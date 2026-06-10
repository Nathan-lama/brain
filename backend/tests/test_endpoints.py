import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from seed_determinism import IDS, seed
from src.database import DATABASE_URL, get_db
from src.main import app
from src.models import Node

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_graph_endpoints():
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

    # Give all nodes simulated embeddings and set sorting order (d2 certain, d1 fort, b1/c1 moyen, p1 faible)
    async with test_session_local() as session:
        nodes_res = await session.execute(select(Node))
        nodes = nodes_res.scalars().all()
        from src.models import TierKind

        # Generate some synthetic embeddings where d1 and d2 are very close, and p1 is far
        for n in nodes:
            emb = [0.0] * 768
            if n.id == IDS["d1"]:
                emb[0] = 1.0
                n.tier = TierKind.FORT
                n.weight = 0.80
            elif n.id == IDS["d2"]:
                emb[0] = 0.95
                emb[1] = 0.05
                n.tier = TierKind.CERTAIN
                n.weight = 0.95
            elif n.id == IDS["b1"]:
                emb[0] = 0.70
                emb[1] = 0.30
                n.tier = TierKind.MOYEN
                n.weight = 0.60
            elif n.id == IDS["c1"]:
                emb[0] = 0.60
                emb[1] = 0.40
                n.tier = TierKind.MOYEN
                n.weight = 0.60
            else:  # p1
                emb[0] = -0.5
                emb[1] = 0.866
                n.tier = TierKind.FAIBLE
                n.weight = 0.40
            n.embedding = emb
        await session.commit()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Test 1: GET /graph
            res_graph = await client.get("/graph")
            assert res_graph.status_code == 200
            graph = res_graph.json()
            assert len(graph["nodes"]) == 5
            # We expect flat edges:
            # ra1 has 3 premises (d1, d2, b1) and conclusion c1 -> 3 edges: d1->c1, d2->c1, b1->c1 (relation: 'soutient')
            # ca1 has 1 conflict from p1 to c1 -> 1 edge: p1->c1 (relation: 'contredit')
            # Total 4 flat edges
            assert len(graph["edges"]) == 4
            for edge in graph["edges"]:
                assert edge["scheme_id"] is not None
                if edge["source"] == str(IDS["p1"]):
                    assert edge["target"] == str(IDS["c1"])
                    assert edge["relation"] == "contredit"
                else:
                    assert edge["target"] == str(IDS["c1"])
                    assert edge["relation"] == "soutient"

            # Test 1b: GET /graph with filtering
            res_graph_filtered = await client.get("/graph?domain=climat")
            assert res_graph_filtered.status_code == 200
            graph_f = res_graph_filtered.json()
            # Only d1 and d2 have domain climat, so nodes count is 2
            assert len(graph_f["nodes"]) == 2
            # Since conclusion c1 is excluded, there should be 0 edges returned (both endpoints must exist in the node list)
            assert len(graph_f["edges"]) == 0

            # Test 2: GET /nodes paginated
            res_nodes = await client.get(
                "/nodes?page=1&limit=2&sort_by=confidence&order=desc"
            )
            assert res_nodes.status_code == 200
            nodes_page = res_nodes.json()
            assert nodes_page["total"] == 5
            assert nodes_page["limit"] == 2
            assert len(nodes_page["items"]) == 2
            # The highest weight is d2 (0.95), then d1 (0.80)
            assert nodes_page["items"][0]["id"] == str(IDS["d2"])
            assert nodes_page["items"][1]["id"] == str(IDS["d1"])

            # Test 3: GET /nodes/{id} detail
            res_detail = await client.get(f"/nodes/{IDS['c1']}")
            assert res_detail.status_code == 200
            detail = res_detail.json()
            assert detail["node"]["id"] == str(IDS["c1"])
            # c1 has incoming connections: d1, d2, b1 (via ra1), and p1 (via ca1)
            # Total 4 incoming neighbors, 0 outgoing neighbors
            assert len(detail["neighbors"]) == 4
            incoming = [
                nb for nb in detail["neighbors"] if nb["direction"] == "incoming"
            ]
            assert len(incoming) == 4
            p1_nb = [nb for nb in incoming if nb["node"]["id"] == str(IDS["p1"])]
            assert len(p1_nb) == 1
            assert p1_nb[0]["relation"] == "contredit"

            # Test 4: GET /nodes/{id}/related suggestions
            # For d1: neighbors are c1. So related should exclude d1 and c1.
            # Similar nodes should be d2 (emb close to d1), b1, p1.
            res_related = await client.get(f"/nodes/{IDS['d1']}/related?k=3")
            assert res_related.status_code == 200
            related = res_related.json()
            assert len(related) == 3
            # Closest should be d2
            assert related[0]["node"]["id"] == str(IDS["d2"])
            assert related[0]["similarity"] > 0.95

            # Test 5: 404 handler
            res_404 = await client.get(f"/nodes/{uuid.uuid4()}")
            assert res_404.status_code == 404

    finally:
        app.dependency_overrides.clear()
        await test_engine.dispose()
