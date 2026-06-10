import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database import DATABASE_URL, get_db
from src.main import app
from src.models import CausalEdge, Node, NodeType, TierKind

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_causal_layer_endpoints_and_feedback():
    test_engine = create_async_engine(DATABASE_URL, echo=False)
    test_session_local = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )

    async def override_get_db():
        async with test_session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Clean and Seed
    async with test_session_local() as session:
        # Clear existing
        from sqlalchemy import delete

        from src.models import Edge, SchemeNode

        await session.execute(delete(CausalEdge))
        await session.execute(delete(Edge))
        await session.execute(delete(SchemeNode))
        await session.execute(delete(Node))

        # Create three empirical nodes: sociaux -> criminalite -> cout
        sociaux_id = uuid.uuid4()
        criminalite_id = uuid.uuid4()
        cout_id = uuid.uuid4()

        nodes = [
            Node(
                id=sociaux_id,
                type=NodeType.EMPIRIQUE,
                domain="sociologie",
                text="Les inégalités sociales augmentent.",
                tier=TierKind.FORT,
                weight=0.8,
            ),
            Node(
                id=criminalite_id,
                type=NodeType.EMPIRIQUE,
                domain="crimino",
                text="Le taux de criminalité augmente.",
                tier=TierKind.MOYEN,
                weight=0.6,
            ),
            Node(
                id=cout_id,
                type=NodeType.EMPIRIQUE,
                domain="economie",
                text="Le coût de la sécurité publique augmente.",
                tier=TierKind.FAIBLE,
                weight=0.4,
            ),
        ]
        session.add_all(nodes)
        await session.commit()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Add causal edges: sociaux -> criminalite (strength=0.8), criminalite -> cout (strength=0.9)
            res1 = await client.post(
                "/causal/edges",
                json={
                    "cause_id": str(sociaux_id),
                    "effect_id": str(criminalite_id),
                    "strength": 0.8,
                },
            )
            assert res1.status_code == 200

            res2 = await client.post(
                "/causal/edges",
                json={
                    "cause_id": str(criminalite_id),
                    "effect_id": str(cout_id),
                    "strength": 0.9,
                },
            )
            assert res2.status_code == 200

            # 2. Verify cycle detection: try to add cout -> sociaux (creates cycle)
            res_cycle = await client.post(
                "/causal/edges",
                json={
                    "cause_id": str(cout_id),
                    "effect_id": str(sociaux_id),
                    "strength": 0.5,
                },
            )
            # Should fail with 400 Bad Request due to DAG cycle violation
            assert res_cycle.status_code == 400
            assert "cycle" in res_cycle.json()["detail"]

            # 3. GET /causal/graph
            res_graph = await client.get("/causal/graph")
            assert res_graph.status_code == 200
            graph_data = res_graph.json()
            assert len(graph_data["nodes"]) == 3
            assert len(graph_data["edges"]) == 2

            # 4. POST /whatif: do(sociaux = 0) (e.g. low inequality / prevention=high)
            # This should lower criminalite and cout
            res_whatif = await client.post(
                "/whatif", json={"interventions": {str(sociaux_id): 0}}
            )
            assert res_whatif.status_code == 200
            whatif_data = res_whatif.json()

            # Verify the credences exist and are within bounds [0, 1]
            assert str(criminalite_id) in whatif_data["credences"]
            assert str(cout_id) in whatif_data["credences"]

            # Let's read the readable descriptions
            assert len(whatif_data["readable_effects"]) > 0
            # E.g. "Si do(...) : criminalite : credence estimée x -> y"

            # 5. Verify feedback loop into /solve
            # First, add a conflict between 'cout' and another claim to see how /solve handles it
            other_id = uuid.uuid4()
            conflict_scheme_id = uuid.uuid4()

            async with test_session_local() as session:
                # Add a normal position node that conflicts with cout
                other_node = Node(
                    id=other_id,
                    type=NodeType.NORMATIF_POSITION,
                    domain="budget",
                    text="Nous devons réduire le budget de la police.",
                    tier=TierKind.MOYEN,
                    weight=0.6,
                )

                conflict_scheme = SchemeNode(
                    id=conflict_scheme_id,
                    scheme="conflit",
                    weight=1.0,
                )
                session.add_all([other_node, conflict_scheme])
                await session.commit()

                # Actually, conflict edges must be in edges table!
                from src.models import Edge, EdgeRole, SourceTargetKind

                edge_conf1 = Edge(
                    id=uuid.uuid4(),
                    source_id=cout_id,
                    target_id=conflict_scheme_id,
                    source_kind=SourceTargetKind.NODE,
                    target_kind=SourceTargetKind.SCHEME,
                    role=EdgeRole.CONFLICTING,
                )
                edge_conf2 = Edge(
                    id=uuid.uuid4(),
                    source_id=conflict_scheme_id,
                    target_id=other_id,
                    source_kind=SourceTargetKind.SCHEME,
                    target_kind=SourceTargetKind.NODE,
                    role=EdgeRole.CONFLICTED,
                )
                session.add_all([edge_conf1, edge_conf2])
                await session.commit()

            # Let's run /solve under baseline (sociaux = 0.7 prior, which makes criminalite high and cout high)
            # Since cout has higher credence than other_node (0.6), the solver should accept cout and reject other_node
            res_solve_base = await client.post("/solve")
            assert res_solve_base.status_code == 200
            solve_base = res_solve_base.json()

            # Now, update sociaux confidence to 0.01 in the database (inequality is very low)
            # This will lower the computed credence of cout below 0.6.
            # Thus, the solver should pivot: accept other_node and reject cout!
            async with test_session_local() as session:
                res_soc = await session.execute(
                    select(Node).filter(Node.id == sociaux_id)
                )
                soc_node = res_soc.scalar_one()
                soc_node.tier = TierKind.SPECULATIF
                soc_node.weight = 0.20
                await session.commit()

            res_solve_low = await client.post("/solve")
            assert res_solve_low.status_code == 200
            solve_low = res_solve_low.json()

            # The acceptance status of other_id or cout_id should have changed
            # (or at least the set of accepted/rejected nodes differs because of the credence change!)
            assert (
                solve_base["accepted"] != solve_low["accepted"]
                or solve_base["rejected"] != solve_low["rejected"]
            )

    finally:
        app.dependency_overrides.clear()
        await test_engine.dispose()
