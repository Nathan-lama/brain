import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database import DATABASE_URL, get_db
from src.main import app
from src.models import (
    CausalEdge,
    Edge,
    EdgeRole,
    Node,
    NodeType,
    SchemeNode,
    SchemeStrength,
    SchemeType,
    SourceTargetKind,
    TierKind,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_quinian_tie_break():
    test_engine = create_async_engine(DATABASE_URL, echo=False)
    test_session_local = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )

    async def override_get_db():
        async with test_session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with test_session_local() as session:
        from sqlalchemy import delete

        # Clean up database first
        await session.execute(delete(CausalEdge))
        await session.execute(delete(Edge))
        await session.execute(delete(SchemeNode))
        await session.execute(delete(Node))
        await session.commit()

        # Nodes
        # P (descriptif, palier certain/rang 5)
        # C (descriptif, palier faible/rang 2)
        # D (descriptif, palier certain/rang 5)
        # D2 (descriptif, palier certain/rang 5)
        p_id = uuid.uuid5(uuid.NAMESPACE_DNS, "P")
        c_id = uuid.uuid5(uuid.NAMESPACE_DNS, "C")
        d_id = uuid.uuid5(uuid.NAMESPACE_DNS, "D")
        d2_id = uuid.uuid5(uuid.NAMESPACE_DNS, "D2")

        p_node = Node(
            id=p_id,
            type=NodeType.DESCRIPTIF,
            domain="quinian",
            text="Prémisse P",
            tier=TierKind.CERTAIN,
            weight=0.95,
        )
        c_node = Node(
            id=c_id,
            type=NodeType.DESCRIPTIF,
            domain="quinian",
            text="Conclusion C",
            tier=TierKind.FAIBLE,
            weight=0.20,
        )
        d_node = Node(
            id=d_id,
            type=NodeType.DESCRIPTIF,
            domain="quinian",
            text="Thèse D",
            tier=TierKind.CERTAIN,
            weight=0.95,
        )
        d2_node = Node(
            id=d2_id,
            type=NodeType.DESCRIPTIF,
            domain="quinian",
            text="Thèse D2",
            tier=TierKind.CERTAIN,
            weight=0.95,
        )
        session.add_all([p_node, c_node, d_node, d2_node])
        await session.flush()

        # Scheme nodes
        # inf1: inference déductive P ⊢ C
        # conflit: conflit (quasi-hard) C × D
        # conflit2: conflit (quasi-hard) C × D2
        inf_id = uuid.uuid5(uuid.NAMESPACE_DNS, "inf")
        conflit_id = uuid.uuid5(uuid.NAMESPACE_DNS, "conflit")
        conflit2_id = uuid.uuid5(uuid.NAMESPACE_DNS, "conflit2")

        inf_node = SchemeNode(
            id=inf_id,
            scheme=SchemeType.INFERENCE,
            strength=SchemeStrength.DEDUCTIF,
            weight=5.0,
        )
        conflit_node = SchemeNode(
            id=conflit_id,
            scheme=SchemeType.CONFLIT,
            weight=1.0,
        )
        conflit2_node = SchemeNode(
            id=conflit2_id,
            scheme=SchemeType.CONFLIT,
            weight=1.0,
        )
        session.add_all([inf_node, conflit_node, conflit2_node])
        await session.flush()

        # Edges
        # P -> inf -> C
        # C -> conflit, D -> conflit
        # C -> conflit2, D2 -> conflit2
        edges = [
            Edge(
                id=uuid.uuid4(),
                source_id=p_id,
                target_id=inf_id,
                source_kind=SourceTargetKind.NODE,
                target_kind=SourceTargetKind.SCHEME,
                role=EdgeRole.PREMISE,
            ),
            Edge(
                id=uuid.uuid4(),
                source_id=inf_id,
                target_id=c_id,
                source_kind=SourceTargetKind.SCHEME,
                target_kind=SourceTargetKind.NODE,
                role=EdgeRole.CONCLUSION,
            ),
            # C x D
            Edge(
                id=uuid.uuid4(),
                source_id=c_id,
                target_id=conflit_id,
                source_kind=SourceTargetKind.NODE,
                target_kind=SourceTargetKind.SCHEME,
                role=EdgeRole.CONFLICTING,
            ),
            Edge(
                id=uuid.uuid4(),
                source_id=conflit_id,
                target_id=d_id,
                source_kind=SourceTargetKind.SCHEME,
                target_kind=SourceTargetKind.NODE,
                role=EdgeRole.CONFLICTED,
            ),
            # C x D2
            Edge(
                id=uuid.uuid4(),
                source_id=c_id,
                target_id=conflit2_id,
                source_kind=SourceTargetKind.NODE,
                target_kind=SourceTargetKind.SCHEME,
                role=EdgeRole.CONFLICTING,
            ),
            Edge(
                id=uuid.uuid4(),
                source_id=conflit2_id,
                target_id=d2_id,
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
            res = await client.post("/solve")
            assert res.status_code == 200
            data = res.json()

            # P must be rejected
            assert str(p_id) in data["rejected"]
            # D and D2 must be accepted
            assert str(d_id) in data["accepted"]
            assert str(d2_id) in data["accepted"]
            # C must be rejected
            assert str(c_id) in data["rejected"]

            # NO deductive inference in violated_constraints
            for vc in data["violated_constraints"]:
                assert vc["scheme_id"] != str(inf_id)
            assert data["incoherence_score"] == 0.0

            # Score checks: D accepted (rank 5 * SCALE = 50000), D2 accepted (rank 5 * SCALE = 50000)
            # Implication satisfied (adds 5.0 * SCALE = 50000)
            # Two conflicts satisfied (adds 200 * SCALE = 200000)
            # DEDUCTIVE_TIE_BREAK adds 1 to the objective.
            # So (300000 + 1) / 10000 = 30.0001, rounded to 3 decimal places = 30.0
            # Wait, 100 * SCALE * 2 = 200 * SCALE.
            # Ranks = 5 + 5 = 10 * SCALE.
            # Implication = 5 * SCALE.
            # Total objective = 215 * SCALE = 2,150,000.
            # Score reported by solver: ObjectiveValue / SCALE = 215.0
            assert data["score"] == 215.0

    finally:
        app.dependency_overrides.clear()
        await test_engine.dispose()
