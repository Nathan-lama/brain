import json
import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database import DATABASE_URL, get_db
from src.main import app
from src.models import BeliefSnapshot, Edge, Node, SchemeNode

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def load_payload():
    filepath = os.path.join(os.path.dirname(__file__), "../../determinism.json")
    with open(filepath, encoding="utf-8") as f:
        return json.load(f)


async def test_import_and_deduplication():
    # Load determinism JSON
    payload = load_payload()

    # Create a test engine and sessionmaker bound to the current running event loop
    test_engine = create_async_engine(DATABASE_URL, echo=False)
    test_session_local = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )

    # Override get_db dependency
    async def override_get_db():
        async with test_session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Clear database for test isolation
    async with test_session_local() as session:
        await session.execute(delete(Edge))
        await session.execute(delete(SchemeNode))
        await session.execute(delete(Node))
        await session.execute(delete(BeliefSnapshot))
        await session.commit()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # First import
            res = await client.post("/import?dedup=false", json=payload)
            assert res.status_code == 200
            summary = res.json()
            assert summary["nodes_created"] == 5
            assert summary["nodes_updated"] == 0
            assert summary["nodes_merged"] == 0
            assert summary["schemes_created_or_updated"] == 2

            # Verify database state
            async with test_session_local() as session:
                # Nodes count
                nodes_res = await session.execute(select(Node))
                nodes = nodes_res.scalars().all()
                assert len(nodes) == 5
                for node in nodes:
                    assert node.embedding is not None
                    assert len(node.embedding) == 768

                # Schemes count
                schemes_res = await session.execute(select(SchemeNode))
                schemes = schemes_res.scalars().all()
                assert len(schemes) == 2

                # Edges count
                edges_res = await session.execute(select(Edge))
                edges = edges_res.scalars().all()
                assert len(edges) == 6

            # Re-import (idempotent, no duplicates)
            res_re = await client.post("/import?dedup=false", json=payload)
            assert res_re.status_code == 200
            summary_re = res_re.json()
            assert summary_re["nodes_created"] == 0
            assert summary_re["nodes_updated"] == 5
            assert summary_re["nodes_merged"] == 0

            # Snapshot test
            res_snap = await client.post("/snapshot?label=TestSnapshot")
            assert res_snap.status_code == 200
            snap = res_snap.json()
            assert snap["label"] == "TestSnapshot"
            assert "id" in snap

            # Verify snapshot exists in database
            async with test_session_local() as session:
                snap_res = await session.execute(
                    select(BeliefSnapshot).filter(
                        BeliefSnapshot.label == "TestSnapshot"
                    )
                )
                snapshots = snap_res.scalars().all()
                assert len(snapshots) == 1
                assert snapshots[0].payload["nodes"] is not None

            # Test Semantic Deduplication (dedup=true)
            similar_node_id = uuid.uuid4()
            dedup_payload = {
                "nodes": [
                    {
                        "id": str(similar_node_id),
                        "type": "descriptif",
                        "domain": "climat",
                        "text": "Les emissions de CO2 réchauffent l'atmosphere.",
                        "confidence": 0.96,
                    }
                ],
                "scheme_nodes": [],
            }

            res_dedup = await client.post("/import?dedup=true", json=dedup_payload)
            assert res_dedup.status_code == 200
            summary_dedup = res_dedup.json()
            assert summary_dedup["nodes_created"] == 0
            assert summary_dedup["nodes_merged"] == 1
            assert summary_dedup["nodes_updated"] == 0

    finally:
        app.dependency_overrides.clear()
        await test_engine.dispose()
