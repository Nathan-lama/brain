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


async def test_versioning_and_snapshot_flow():
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
            # 1. Verify initially we have no events
            res_events = await client.get("/events")
            assert res_events.status_code == 200
            events = res_events.json()
            # Depending on if seeding runs via SQLAlchemy models or directly, we might have events or not.
            # In our seed script, we write directly/normally, so let's check events before/after.
            initial_event_count = len(events)

            # 2. Resolve a tension
            res_resolve = await client.post(
                "/tensions/resolve",
                json={"action": "reviser_node", "node_id": str(IDS["p1"])},
            )
            assert res_resolve.status_code == 200
            diff = res_resolve.json()

            # Check TensionDiffOut structure
            assert "tensions_resolues" in diff
            assert "tensions_nouvelles" in diff
            assert "claims_affectes" in diff

            # Verify direct conflict was resolved
            resolved_tensions = diff["tensions_resolues"]
            assert len(resolved_tensions) == 1
            assert resolved_tensions[0]["scheme_id"] == str(IDS["ca1"])

            # Check affected claims
            claim_ids = [c["id"] for c in diff["claims_affectes"]]
            assert str(IDS["p1"]) in claim_ids

            # 3. Check event was logged
            res_events_after = await client.get("/events")
            events_after = res_events_after.json()
            assert len(events_after) > initial_event_count
            update_event = [
                e
                for e in events_after
                if e["entity_id"] == str(IDS["p1"]) and e["op"] == "update"
            ][0]
            assert update_event["before"]["weight"] > 0.0
            assert update_event["after"]["weight"] == 0.0

            # 4. Create Snapshot 1 (Original/Modified State where p1 is 0.0)
            res_snap1 = await client.post("/snapshot", params={"label": "Snap1"})
            assert res_snap1.status_code == 200
            snap1_id = res_snap1.json()["id"]

            # 5. Restore back to original seed by running seed again
            async with test_session_local() as session:
                await seed(session)

            # Create Snapshot 2 (where p1 is back to high confidence)
            res_snap2 = await client.post("/snapshot", params={"label": "Snap2"})
            assert res_snap2.status_code == 200
            snap2_id = res_snap2.json()["id"]

            # 6. Diff snapshots
            res_diff = await client.get(
                "/snapshots/diff", params={"from": snap2_id, "to": snap1_id}
            )
            assert res_diff.status_code == 200
            snap_diff = res_diff.json()

            # Since p1 went from 1.0 (or high confidence) in snap2 to 0.0 in snap1
            assert len(snap_diff["claims_modifies"]) >= 1
            modified_ids = [n["id"] for n in snap_diff["claims_modifies"]]
            assert str(IDS["p1"]) in modified_ids

            # Tensions should be resolved between snap2 (has conflict) and snap1 (no conflict)
            assert len(snap_diff["tensions_resolues"]) == 1

            # 7. Restore snapshot 1
            res_restore = await client.post(f"/snapshots/{snap1_id}/restore")
            assert res_restore.status_code == 200

            # Verify p1 confidence is 0.0 in DB again
            async with test_session_local() as session:
                res_node = await session.execute(
                    select(Node).filter(Node.id == IDS["p1"])
                )
                node = res_node.scalar_one()
                assert node.weight == 0.0

    finally:
        app.dependency_overrides.clear()
        await test_engine.dispose()
