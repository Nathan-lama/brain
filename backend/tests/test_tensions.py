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


async def test_tension_detection_and_resolution():
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
            # 1. Query GET /tensions -> Should detect 1 direct conflict tension
            res_tensions = await client.get("/tensions")
            assert res_tensions.status_code == 200
            tensions = res_tensions.json()

            assert len(tensions) == 1
            tension = tensions[0]
            assert tension["type"] == "conflit_direct"
            assert tension["scheme_id"] == str(IDS["ca1"])
            assert tension["paradoxe_assume"] is False

            # Claims involved should be p1 (croissance) and c1 (réduire CO2)
            claim_ids = [c["id"] for c in tension["claims"]]
            assert str(IDS["p1"]) in claim_ids
            assert str(IDS["c1"]) in claim_ids

            # Mediator ponts should include b1
            pont_ids = [p["id"] for p in tension["ponts"]]
            assert str(IDS["b1"]) in pont_ids

            # 2. Resolve tension: revise node p1
            res_resolve = await client.post(
                "/tensions/resolve",
                json={"action": "reviser_node", "node_id": str(IDS["p1"])},
            )
            assert res_resolve.status_code == 200

            # 3. Query GET /tensions again -> Should be 0 tensions now
            res_tensions_after = await client.get("/tensions")
            assert res_tensions_after.status_code == 200
            tensions_after = res_tensions_after.json()
            assert len(tensions_after) == 0

            # Verify in DB that p1 confidence is 0.0
            async with test_session_local() as session:
                res_node = await session.execute(
                    select(Node).filter(Node.id == IDS["p1"])
                )
                node = res_node.scalar_one()
                assert node.weight == 0.0

            # 4. Re-seed to reset graph
            async with test_session_local() as session:
                await seed(session)

            # 5. Resolve tension: accept paradox for scheme ca1
            res_resolve_paradox = await client.post(
                "/tensions/resolve",
                json={"action": "accepter_paradoxe", "scheme_id": str(IDS["ca1"])},
            )
            assert res_resolve_paradox.status_code == 200

            # 6. Query GET /tensions again -> Should return the tension but with paradoxe_assume = True
            res_tensions_paradox = await client.get("/tensions")
            assert res_tensions_paradox.status_code == 200
            tensions_paradox = res_tensions_paradox.json()
            assert len(tensions_paradox) == 1
            assert tensions_paradox[0]["paradoxe_assume"] is True

            # Verify in DB that scheme node ca1 has paradoxe_assume set to True in metadata
            async with test_session_local() as session:
                res_scheme = await session.execute(
                    select(SchemeNode).filter(SchemeNode.id == IDS["ca1"])
                )
                scheme = res_scheme.scalar_one()
                assert scheme.metadata_.get("paradoxe_assume") is True

    finally:
        app.dependency_overrides.clear()
        await test_engine.dispose()
