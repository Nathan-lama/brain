import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from seed_determinism import seed
from src.database import DATABASE_URL
from src.models import Edge, Node, SchemeNode
from src.schemas import EdgeOut, GraphExport, NodeOut, SchemeNodeOut

# Use anyio as the async backend for tests
pytestmark = pytest.mark.anyio


async def test_seeding_and_graph_topology():
    test_engine = create_async_engine(DATABASE_URL, echo=False)
    test_session_local = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )

    # 1. Run the seed script logic using the local session
    async with test_session_local() as session:
        await seed(session)

    # 2. Assert counts and data in database
    async with test_session_local() as session:
        # Fetch all nodes
        nodes_result = await session.execute(select(Node))
        nodes = nodes_result.scalars().all()
        assert len(nodes) == 5

        # Fetch all scheme nodes
        schemes_result = await session.execute(select(SchemeNode))
        schemes = schemes_result.scalars().all()
        assert len(schemes) == 2

        # Fetch all edges
        edges_result = await session.execute(select(Edge))
        edges = edges_result.scalars().all()
        assert len(edges) == 6

        # Find specific node and scheme node by text/attributes
        d1_nodes = [
            n for n in nodes if n.type.value == "descriptif" and "émissions" in n.text
        ]
        assert len(d1_nodes) == 1
        d1 = d1_nodes[0]

        ra1_schemes = [s for s in schemes if s.scheme.value == "inference"]
        assert len(ra1_schemes) == 1
        ra1 = ra1_schemes[0]

        # Check edge connecting d1 to ra1 (premise)
        d1_ra1_edges = [
            e for e in edges if e.source_id == d1.id and e.target_id == ra1.id
        ]
        assert len(d1_ra1_edges) == 1
        assert d1_ra1_edges[0].role.value == "premise"
        assert d1_ra1_edges[0].source_kind.value == "node"
        assert d1_ra1_edges[0].target_kind.value == "scheme"

        # 3. Verify Pydantic serialization / GraphExport
        export = GraphExport(
            nodes=[NodeOut.model_validate(n) for n in nodes],
            scheme_nodes=[SchemeNodeOut.model_validate(s) for s in schemes],
            edges=[EdgeOut.model_validate(e) for e in edges],
        )
        assert len(export.nodes) == 5
        assert len(export.scheme_nodes) == 2
        assert len(export.edges) == 6

    await test_engine.dispose()
