import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from seed_determinism import IDS, seed
from src.database import DATABASE_URL, get_db
from src.main import app
from src.models import Node, SchemeNode

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_coherence_solver_endpoints():
    test_engine = create_async_engine(DATABASE_URL, echo=False)
    test_session_local = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )

    async def override_get_db():
        async with test_session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # 1. Seed the database
    async with test_session_local() as session:
        await seed(session)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 2. Query POST /solve -> Should run solver
            res_solve = await client.post("/solve")
            assert res_solve.status_code == 200
            solve_data = res_solve.json()

            # Verify that c1 is accepted and p1 is rejected (because c1 is highly supported)
            assert str(IDS["c1"]) in solve_data["accepted"]
            assert str(IDS["p1"]) in solve_data["rejected"]
            assert (
                solve_data["incoherence_score"] == 0.0
            )  # no soft implication violated
            assert len(solve_data["violated_constraints"]) == 0
            assert "arbitrated_tensions" in solve_data

            # 3. Update p1 tier/weight to make it dominate, and reduce c1 & ra1
            async with test_session_local() as session:
                from src.models import TierKind

                res_p1 = await session.execute(
                    select(Node).filter(Node.id == IDS["p1"])
                )
                p1_node = res_p1.scalar_one()
                p1_node.tier = TierKind.CERTAIN
                p1_node.weight = 0.95

                res_c1 = await session.execute(
                    select(Node).filter(Node.id == IDS["c1"])
                )
                c1_node = res_c1.scalar_one()
                c1_node.tier = TierKind.SPECULATIF
                c1_node.weight = 0.20

                # Reduce ra1 weight to 0.01
                res_ra1 = await session.execute(
                    select(SchemeNode).filter(SchemeNode.id == IDS["ra1"])
                )
                ra1_node = res_ra1.scalar_one()
                ra1_node.weight = 0.01

                await session.commit()

            # 4. Resolve again -> Should pivot: accept p1, reject c1, and violate the soft implications from d1,d2,b1
            res_solve2 = await client.post("/solve")
            assert res_solve2.status_code == 200
            solve_data2 = res_solve2.json()

            assert str(IDS["p1"]) in solve_data2["accepted"]
            assert str(IDS["c1"]) in solve_data2["rejected"]
            # Since c1 is rejected, the implication (d1 AND d2 AND b1) => c1 is violated.
            # Total incoherence_score should be 1 * ra1_node.weight = 0.01
            assert solve_data2["incoherence_score"] == 0.01
            assert len(solve_data2["violated_constraints"]) == 1
            assert (
                abs(
                    sum(vc["cost"] for vc in solve_data2["violated_constraints"])
                    - solve_data2["incoherence_score"]
                )
                < 1e-5
            )

            # 5. Query GET /solve/alternatives?n=3 -> Should return alternative solutions
            res_alts = await client.get("/solve/alternatives?n=2")
            assert res_alts.status_code == 200
            alts_data = res_alts.json()

            assert len(alts_data) > 0
            # Each alternative solution should have a solution_index, accepted, rejected, differs_accepted, differs_rejected, etc.
            for alt in alts_data:
                assert "solution_index" in alt
                assert "accepted" in alt
                assert "rejected" in alt
                assert "differs_accepted" in alt
                assert "differs_rejected" in alt
                assert "arbitrated_tensions" in alt
                assert "violated_constraints" in alt
                assert "incoherence_score" in alt
                # Assert invariant: sum(costs) == incoherence_score
                assert (
                    abs(
                        sum(vc["cost"] for vc in alt["violated_constraints"])
                        - alt["incoherence_score"]
                    )
                    < 1e-5
                )

    finally:
        app.dependency_overrides.clear()
        await test_engine.dispose()


async def test_paradox_baseline_tension():
    import uuid

    test_engine = create_async_engine(DATABASE_URL, echo=False)
    test_session_local = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )

    async def override_get_db():
        async with test_session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Seed the paradox graph
    async with test_session_local() as session:
        from sqlalchemy import delete

        from src.models import (
            CausalEdge,
            Edge,
            EdgeRole,
            Node,
            NodeType,
            SchemeNode,
            SchemeType,
            SourceTargetKind,
            TierKind,
        )

        await session.execute(delete(CausalEdge))
        await session.execute(delete(Edge))
        await session.execute(delete(SchemeNode))
        await session.execute(delete(Node))
        await session.commit()

        # Create nodes
        p1_id = uuid.uuid5(uuid.NAMESPACE_DNS, "p1")
        p2_id = uuid.uuid5(uuid.NAMESPACE_DNS, "p2")
        cA_id = uuid.uuid5(uuid.NAMESPACE_DNS, "cA")
        cB_id = uuid.uuid5(uuid.NAMESPACE_DNS, "cB")

        p1 = Node(
            id=p1_id,
            type=NodeType.DESCRIPTIF,
            domain="paradoxe",
            text="La physique macroscopique obéit à des lois déterministes.",
            tier=TierKind.CERTAIN,
            weight=0.95,
            metadata_={"imported_id": "p1"},
        )
        p2 = Node(
            id=p2_id,
            type=NodeType.DESCRIPTIF,
            domain="paradoxe",
            text="L'introspection humaine témoigne d'un sentiment d'agence.",
            tier=TierKind.CERTAIN,
            weight=0.95,
            metadata_={"imported_id": "p2"},
        )
        cA = Node(
            id=cA_id,
            type=NodeType.NORMATIF_CONCLUSION,
            domain="paradoxe",
            text="Nous devons abandonner la notion de choix moral ultime.",
            tier=TierKind.MOYEN,
            weight=0.60,
            metadata_={"imported_id": "cA"},
        )
        cB = Node(
            id=cB_id,
            type=NodeType.NORMATIF_CONCLUSION,
            domain="paradoxe",
            text="Nous devons préserver la notion de responsabilité morale rétributive.",
            tier=TierKind.MOYEN,
            weight=0.60,
            metadata_={"imported_id": "cB"},
        )
        session.add_all([p1, p2, cA, cB])
        await session.flush()

        # Scheme nodes
        inf1_id = uuid.uuid5(uuid.NAMESPACE_DNS, "inf1")
        inf2_id = uuid.uuid5(uuid.NAMESPACE_DNS, "inf2")
        conflit_id = uuid.uuid5(uuid.NAMESPACE_DNS, "conflit")

        from src.models import SchemeStrength

        inf1 = SchemeNode(
            id=inf1_id,
            scheme=SchemeType.INFERENCE,
            strength=SchemeStrength.DEFAISABLE_FORT,
            weight=2.0,
            metadata_={"imported_id": "inf1"},
        )
        inf2 = SchemeNode(
            id=inf2_id,
            scheme=SchemeType.INFERENCE,
            strength=SchemeStrength.DEFAISABLE_FORT,
            weight=2.0,
            metadata_={"imported_id": "inf2"},
        )
        conflit = SchemeNode(
            id=conflit_id,
            scheme=SchemeType.CONFLIT,
            weight=1.0,
            metadata_={"imported_id": "conflit"},
        )
        session.add_all([inf1, inf2, conflit])
        await session.flush()

        # Edges
        edges = [
            Edge(
                id=uuid.uuid4(),
                source_id=p1_id,
                target_id=inf1_id,
                source_kind=SourceTargetKind.NODE,
                target_kind=SourceTargetKind.SCHEME,
                role=EdgeRole.PREMISE,
            ),
            Edge(
                id=uuid.uuid4(),
                source_id=inf1_id,
                target_id=cA_id,
                source_kind=SourceTargetKind.SCHEME,
                target_kind=SourceTargetKind.NODE,
                role=EdgeRole.CONCLUSION,
            ),
            Edge(
                id=uuid.uuid4(),
                source_id=p2_id,
                target_id=inf2_id,
                source_kind=SourceTargetKind.NODE,
                target_kind=SourceTargetKind.SCHEME,
                role=EdgeRole.PREMISE,
            ),
            Edge(
                id=uuid.uuid4(),
                source_id=inf2_id,
                target_id=cB_id,
                source_kind=SourceTargetKind.SCHEME,
                target_kind=SourceTargetKind.NODE,
                role=EdgeRole.CONCLUSION,
            ),
            Edge(
                id=uuid.uuid4(),
                source_id=cA_id,
                target_id=conflit_id,
                source_kind=SourceTargetKind.NODE,
                target_kind=SourceTargetKind.SCHEME,
                role=EdgeRole.CONFLICTING,
            ),
            Edge(
                id=uuid.uuid4(),
                source_id=conflit_id,
                target_id=cB_id,
                source_kind=SourceTargetKind.SCHEME,
                target_kind=SourceTargetKind.NODE,
                role=EdgeRole.CONFLICTED,
            ),
        ]
        session.add_all(edges)
        await session.commit()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res_solve = await client.post("/solve")
            assert res_solve.status_code == 200
            data = res_solve.json()

            # Baseline has one logical violation since the paradox is insoluble without violating inf1 or inf2
            assert data["incoherence_score"] == 2.0
            assert len(data["violated_constraints"]) == 1
            assert data["violated_constraints"][0]["cost"] == 2.0

            # One of the two positions must be rejected and therefore "in tension"
            rejected = data["rejected"]
            assert len(rejected) == 1
            rejected_id = rejected[0]
            assert rejected_id in [str(cA_id), str(cB_id)]

            # The rejected node must be part of the violated constraint's node refs
            violation = data["violated_constraints"][0]
            involved_ids = [ref["id"] for ref in violation["node_refs"]]
            assert rejected_id in involved_ids

    finally:
        app.dependency_overrides.clear()
        await test_engine.dispose()


def test_cost_invariant_raises():
    import uuid

    from src.schemas import ViolatedConstraint
    from src.services.solver import CostInvariantViolation, assert_cost_invariant

    vc = ViolatedConstraint(
        constraint_id=uuid.uuid4(),
        scheme_id=uuid.uuid4(),
        kind="inference",
        node_refs=[],
        cost=1.5,
        detail="Test constraint",
    )

    # Matching cost should not raise
    assert_cost_invariant([vc], 1.5)

    # Mismatched cost should raise
    with pytest.raises(CostInvariantViolation) as exc_info:
        assert_cost_invariant([vc], 2.0)
    assert exc_info.value.expected == 1.5
    assert exc_info.value.got == 2.0


async def test_alternatives_deterministic():
    test_engine = create_async_engine(DATABASE_URL, echo=False)
    test_session_local = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )

    async def override_get_db():
        async with test_session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Seed the database
    async with test_session_local() as session:
        await seed(session)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Query alternatives twice
            res1 = await client.get("/solve/alternatives?n=3")
            assert res1.status_code == 200
            data1 = res1.json()

            res2 = await client.get("/solve/alternatives?n=3")
            assert res2.status_code == 200
            data2 = res2.json()

            # Deep equality
            assert data1 == data2
    finally:
        app.dependency_overrides.clear()
        await test_engine.dispose()


async def test_cost_invariant_asserted_on_both_endpoints(monkeypatch):
    import uuid

    test_engine = create_async_engine(DATABASE_URL, echo=False)
    test_session_local = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )

    async def override_get_db():
        async with test_session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Seed the database
    async with test_session_local() as session:
        await seed(session)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Normal conditions (no exceptions)
            res_solve = await client.post("/solve")
            assert res_solve.status_code == 200

            res_alts = await client.get("/solve/alternatives?n=2")
            assert res_alts.status_code == 200

            # 2. Monkeypatch assert_cost_invariant to always raise
            from src.services import solver

            def mock_assert_cost_invariant(violated_constraints, incoherence_score):
                raise solver.CostInvariantViolation(
                    expected=999.0,
                    got=incoherence_score,
                    constraint_ids=[uuid.UUID("d1111111-1111-1111-1111-111111111111")],
                )

            monkeypatch.setattr(
                solver, "assert_cost_invariant", mock_assert_cost_invariant
            )

            # Now both endpoints must return HTTP 500 with custom body
            res_solve_err = await client.post("/solve")
            assert res_solve_err.status_code == 500
            body_solve = res_solve_err.json()
            assert body_solve["expected"] == 999.0
            assert body_solve["constraint_ids"] == [
                "d1111111-1111-1111-1111-111111111111"
            ]

            res_alts_err = await client.get("/solve/alternatives?n=2")
            assert res_alts_err.status_code == 500
            body_alts = res_alts_err.json()
            assert body_alts["expected"] == 999.0
            assert body_alts["constraint_ids"] == [
                "d1111111-1111-1111-1111-111111111111"
            ]

    finally:
        app.dependency_overrides.clear()
        await test_engine.dispose()


def test_quinian_static_invariant():
    from src.models import STRENGTH_TO_WEIGHT, SchemeStrength
    from src.services.solver import TIER_RANKS

    max_rank = max(TIER_RANKS.values())
    deductive_weight = STRENGTH_TO_WEIGHT[SchemeStrength.DEDUCTIF]

    assert max_rank <= deductive_weight, (
        f"La propriété quinienne (le solveur révise les prémisses plutôt que de casser un lien déductif) "
        f"est compromise : le rang maximum des paliers ({max_rank}) dépasse le poids d'un lien déductif ({deductive_weight})."
    )


def test_stake_rank_calculation_and_sorting():
    import uuid

    from src.models import (
        Edge,
        EdgeRole,
        Node,
        NodeType,
        SchemeNode,
        SchemeType,
        SourceTargetKind,
        TierKind,
    )
    from src.services.solver import CoherenceSolverService

    # 1. Verify stake_rank / stake_label calculations (min of node tiers)
    id1 = uuid.uuid4()
    id2 = uuid.uuid4()

    # 5/2 -> 2, "faible"
    n1 = Node(
        id=id1,
        type=NodeType.DESCRIPTIF,
        domain="test",
        text="N1",
        tier=TierKind.CERTAIN,
        weight=1.0,
    )
    n2 = Node(
        id=id2,
        type=NodeType.DESCRIPTIF,
        domain="test",
        text="N2",
        tier=TierKind.FAIBLE,
        weight=1.0,
    )

    s_id = uuid.uuid4()
    s_node = SchemeNode(id=s_id, scheme=SchemeType.CONFLIT, weight=1.0)

    e1 = Edge(
        source_id=id1,
        target_id=s_id,
        source_kind=SourceTargetKind.NODE,
        target_kind=SourceTargetKind.SCHEME,
        role=EdgeRole.CONFLICTING,
    )
    e2 = Edge(
        source_id=s_id,
        target_id=id2,
        source_kind=SourceTargetKind.SCHEME,
        target_kind=SourceTargetKind.NODE,
        role=EdgeRole.CONFLICTED,
    )

    nodes_map = {id1: n1, id2: n2}
    scheme_nodes = [s_node]
    edges = [e1, e2]

    res = CoherenceSolverService._compute_arbitrated_tensions(
        nodes_map=nodes_map, scheme_nodes=scheme_nodes, edges=edges, accepted_ids={id1}
    )

    assert len(res) == 1
    t = res[0]
    assert t.stake_rank == 2
    assert t.stake_label == "faible"
    assert t.kept_node.id == id1
    assert t.discarded_node.id == id2

    # 2. Verify stable ordering (sorting descending by stake_rank, and stable tie-breaking on node IDs)
    uuids = sorted([uuid.uuid4() for _ in range(6)])

    # C_A: kept = uuids[2], discarded = uuids[3], rank = 3 (moyen)
    # C_B: kept = uuids[0], discarded = uuids[1], rank = 3 (moyen)
    # C_C: kept = uuids[4], discarded = uuids[5], rank = 5 (certain)

    n_uuids = {}
    for i, uid in enumerate(uuids):
        tier = TierKind.CERTAIN if i >= 4 else TierKind.MOYEN
        n_uuids[uid] = Node(
            id=uid,
            type=NodeType.DESCRIPTIF,
            domain="test",
            text=f"Node {i}",
            tier=tier,
            weight=1.0,
        )

    s_a = SchemeNode(id=uuid.uuid4(), scheme=SchemeType.CONFLIT, weight=1.0)
    s_b = SchemeNode(id=uuid.uuid4(), scheme=SchemeType.CONFLIT, weight=1.0)
    s_c = SchemeNode(id=uuid.uuid4(), scheme=SchemeType.CONFLIT, weight=1.0)

    edges_list = [
        # C_A
        Edge(
            source_id=uuids[2],
            target_id=s_a.id,
            source_kind=SourceTargetKind.NODE,
            target_kind=SourceTargetKind.SCHEME,
            role=EdgeRole.CONFLICTING,
        ),
        Edge(
            source_id=s_a.id,
            target_id=uuids[3],
            source_kind=SourceTargetKind.SCHEME,
            target_kind=SourceTargetKind.NODE,
            role=EdgeRole.CONFLICTED,
        ),
        # C_B
        Edge(
            source_id=uuids[0],
            target_id=s_b.id,
            source_kind=SourceTargetKind.NODE,
            target_kind=SourceTargetKind.SCHEME,
            role=EdgeRole.CONFLICTING,
        ),
        Edge(
            source_id=s_b.id,
            target_id=uuids[1],
            source_kind=SourceTargetKind.SCHEME,
            target_kind=SourceTargetKind.NODE,
            role=EdgeRole.CONFLICTED,
        ),
        # C_C
        Edge(
            source_id=uuids[4],
            target_id=s_c.id,
            source_kind=SourceTargetKind.NODE,
            target_kind=SourceTargetKind.SCHEME,
            role=EdgeRole.CONFLICTING,
        ),
        Edge(
            source_id=s_c.id,
            target_id=uuids[5],
            source_kind=SourceTargetKind.SCHEME,
            target_kind=SourceTargetKind.NODE,
            role=EdgeRole.CONFLICTED,
        ),
    ]

    accepted = {uuids[0], uuids[2], uuids[4]}

    tensions = CoherenceSolverService._compute_arbitrated_tensions(
        nodes_map=n_uuids,
        scheme_nodes=[s_a, s_b, s_c],
        edges=edges_list,
        accepted_ids=accepted,
    )

    assert len(tensions) == 3
    # Expected ordering: C_C (uuids[4] rank 5) first, then C_B (uuids[0] rank 3), then C_A (uuids[2] rank 3)
    assert tensions[0].kept_node.id == uuids[4]
    assert tensions[0].stake_rank == 5

    assert tensions[1].kept_node.id == uuids[0]
    assert tensions[1].stake_rank == 3

    assert tensions[2].kept_node.id == uuids[2]
    assert tensions[2].stake_rank == 3


async def test_tie_break_bound_guard(monkeypatch):
    import uuid

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    import src.services.solver as solver_module
    from src.database import DATABASE_URL
    from src.models import (
        Edge,
        Node,
        SchemeNode,
        SchemeStrength,
        SchemeType,
    )
    from src.services.solver import CoherenceSolverService

    test_engine = create_async_engine(DATABASE_URL, echo=False)
    test_session_local = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )

    async with test_session_local() as session:
        # Clean up database first to control counts
        await session.execute(delete(Edge))
        await session.execute(delete(SchemeNode))
        await session.execute(delete(Node))
        await session.commit()

        s_node = SchemeNode(
            id=uuid.uuid4(),
            scheme=SchemeType.INFERENCE,
            strength=SchemeStrength.DEDUCTIF,
            weight=5.0,
        )
        session.add(s_node)
        await session.commit()

        # (a) Verify that with default constants, the guard passes
        from src.services.solver import load_graph
        g = await load_graph(session)
        CoherenceSolverService._build_model_pure(g)

        # (b) Verify that if we monkeypatch DEDUCTIVE_TIE_BREAK to be >= SCALE, it raises AssertionError
        monkeypatch.setattr(solver_module, "DEDUCTIVE_TIE_BREAK", 20000)
        with pytest.raises(AssertionError) as exc_info:
            CoherenceSolverService._build_model_pure(g)

        assert "DEDUCTIVE_TIE_BREAK guard violated" in str(exc_info.value)

    await test_engine.dispose()


async def test_alternatives_incoherence_below_baseline():
    import uuid

    from src.models import (
        Edge,
        EdgeRole,
        NodeType,
        SchemeStrength,
        SchemeType,
        SourceTargetKind,
        TierKind,
    )

    test_engine = create_async_engine(DATABASE_URL, echo=False)
    test_session_local = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )

    async def override_get_db():
        async with test_session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Seed custom mini-fixture demonstrating incoherence below baseline
    async with test_session_local() as session:
        from sqlalchemy import delete
        await session.execute(delete(Edge))
        await session.execute(delete(SchemeNode))
        await session.execute(delete(Node))
        await session.commit()

        n1_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        n2_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
        n3_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
        n4_id = uuid.UUID("44444444-4444-4444-4444-444444444444")

        # n1 (rank 3), n2 (rank 3), n3 (rank 1), n4 (rank 5)
        n1 = Node(id=n1_id, type=NodeType.DESCRIPTIF, domain="test", text="n1", tier=TierKind.MOYEN, weight=1.0)
        n2 = Node(id=n2_id, type=NodeType.DESCRIPTIF, domain="test", text="n2", tier=TierKind.MOYEN, weight=1.0)
        n3 = Node(id=n3_id, type=NodeType.DESCRIPTIF, domain="test", text="n3", tier=TierKind.SPECULATIF, weight=1.0)
        n4 = Node(id=n4_id, type=NodeType.DESCRIPTIF, domain="test", text="n4", tier=TierKind.CERTAIN, weight=1.0)

        # Inference: n1 ∧ n2 → n3 (defeasible, weight=2)
        inf_id = uuid.UUID("55555555-5555-5555-5555-555555555555")
        inf = SchemeNode(id=inf_id, scheme=SchemeType.INFERENCE, strength=SchemeStrength.DEFAISABLE_FORT, weight=2.0)

        # Conflict: n3 ↔ n4 (weight=1)
        conflit_id = uuid.UUID("66666666-6666-6666-6666-666666666666")
        conflit = SchemeNode(id=conflit_id, scheme=SchemeType.CONFLIT, weight=1.0)

        session.add_all([n1, n2, n3, n4, inf, conflit])
        await session.commit()

        # Edges
        e1 = Edge(id=uuid.uuid4(), source_id=n1_id, target_id=inf_id, source_kind=SourceTargetKind.NODE, target_kind=SourceTargetKind.SCHEME, role=EdgeRole.PREMISE)
        e2 = Edge(id=uuid.uuid4(), source_id=n2_id, target_id=inf_id, source_kind=SourceTargetKind.NODE, target_kind=SourceTargetKind.SCHEME, role=EdgeRole.PREMISE)
        e3 = Edge(id=uuid.uuid4(), source_id=inf_id, target_id=n3_id, source_kind=SourceTargetKind.SCHEME, target_kind=SourceTargetKind.NODE, role=EdgeRole.CONCLUSION)
        
        e4 = Edge(id=uuid.uuid4(), source_id=n3_id, target_id=conflit_id, source_kind=SourceTargetKind.NODE, target_kind=SourceTargetKind.SCHEME, role=EdgeRole.CONFLICTING)
        e5 = Edge(id=uuid.uuid4(), source_id=conflit_id, target_id=n4_id, source_kind=SourceTargetKind.SCHEME, target_kind=SourceTargetKind.NODE, role=EdgeRole.CONFLICTED)

        session.add_all([e1, e2, e3, e4, e5])
        await session.commit()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Query solve (baseline)
            res_solve = await client.post("/solve")
            assert res_solve.status_code == 200
            solve_data = res_solve.json()
            assert solve_data["incoherence_score"] == 2.0  # I1 is violated because n3 is rejected (due to conflict with certain n4)

            # Query alternatives
            res_alts = await client.get("/solve/alternatives?n=3")
            assert res_alts.status_code == 200
            alts_data = res_alts.json()
            
            # Assert that score is populated, strictly non-increasing (or equal),
            # and at least one alternative has incoherence below baseline (2.0)
            assert len(alts_data) > 0
            has_lower_incoherence = False
            prev_score = float("inf")
            for alt in alts_data:
                assert alt["score"] is not None
                assert alt["score"] <= prev_score
                prev_score = alt["score"]
                if alt["incoherence_score"] < solve_data["incoherence_score"]:
                    has_lower_incoherence = True
            
            assert has_lower_incoherence
    finally:
        app.dependency_overrides.clear()
        await test_engine.dispose()


def test_solve_graph_purity():
    import uuid

    from src.models import (
        EdgeRole,
        NodeType,
        SchemeStrength,
        SchemeType,
        SourceTargetKind,
    )
    from src.services.solver import EdgeRow, GraphData, NodeRow, SchemeRow, solve_graph

    n1_id = uuid.uuid4()
    n2_id = uuid.uuid4()
    n3_id = uuid.uuid4()
    s_id = uuid.uuid4()

    nodes = [
        NodeRow(id=n1_id, type=NodeType.DESCRIPTIF, tier="certain", weight=0.95, text="Premise 1"),
        NodeRow(id=n2_id, type=NodeType.DESCRIPTIF, tier="certain", weight=0.95, text="Premise 2"),
        NodeRow(id=n3_id, type=NodeType.DESCRIPTIF, tier="certain", weight=0.95, text="Conclusion"),
    ]
    schemes = [
        SchemeRow(id=s_id, scheme=SchemeType.INFERENCE, strength=SchemeStrength.DEFAISABLE_FORT, weight=2.0),
    ]
    edges = [
        EdgeRow(source_id=n1_id, source_kind=SourceTargetKind.NODE, target_id=s_id, target_kind=SourceTargetKind.SCHEME, role=EdgeRole.PREMISE),
        EdgeRow(source_id=n2_id, source_kind=SourceTargetKind.NODE, target_id=s_id, target_kind=SourceTargetKind.SCHEME, role=EdgeRole.PREMISE),
        EdgeRow(source_id=s_id, source_kind=SourceTargetKind.SCHEME, target_id=n3_id, target_kind=SourceTargetKind.NODE, role=EdgeRole.CONCLUSION),
    ]

    g = GraphData(nodes=nodes, schemes=schemes, edges=edges, credences={})
    res = solve_graph(g)

    assert res["incoherence_score"] == 0.0
    assert set(res["accepted"]) == {n1_id, n2_id, n3_id}
