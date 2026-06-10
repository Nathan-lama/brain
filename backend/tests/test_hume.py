import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from seed_determinism import seed
from src.database import DATABASE_URL, get_db
from src.main import app
from src.models import (
    Edge,
    Node,
    SchemeNode,
)
from src.services.validation.hume import check_hume

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_check_hume_pure():
    p1_id = uuid.uuid4()
    p2_id = uuid.uuid4()
    c_id = uuid.uuid4()
    inf_id = uuid.uuid4()

    # Case A: Inference descriptive/empirique -> normatif_conclusion (1 violation)
    nodes_a = [
        {"id": p1_id, "type": "descriptif", "metadata": {"imported_id": "p1"}},
        {"id": p2_id, "type": "empirique", "metadata": {"imported_id": "p2"}},
        {"id": c_id, "type": "normatif_conclusion", "metadata": {"imported_id": "c"}},
    ]
    schemes_a = [
        {
            "id": inf_id,
            "scheme": "inference",
            "premises": [str(p1_id), str(p2_id)],
            "conclusion": str(c_id),
        }
    ]
    edges_a = []

    violations_a = check_hume(nodes_a, schemes_a, edges_a)
    assert len(violations_a) == 1
    assert violations_a[0].scheme_id == inf_id
    assert violations_a[0].conclusion.id == c_id

    # Case B: Descriptive/empirique + pont_normatif -> normatif_conclusion (0 violations)
    pont_id = uuid.uuid4()
    nodes_b = [
        {"id": p1_id, "type": "descriptif", "metadata": {"imported_id": "p1"}},
        {"id": pont_id, "type": "pont_normatif", "metadata": {"imported_id": "pont"}},
        {"id": c_id, "type": "normatif_conclusion", "metadata": {"imported_id": "c"}},
    ]
    schemes_b = [
        {
            "id": inf_id,
            "scheme": "inference",
            "premises": [str(p1_id), str(pont_id)],
            "conclusion": str(c_id),
        }
    ]
    violations_b = check_hume(nodes_b, schemes_b, edges_a)
    assert len(violations_b) == 0

    # Case C: premises definitionnel only -> normatif_position (1 violation)
    def_id = uuid.uuid4()
    nodes_c = [
        {"id": def_id, "type": "definitionnel", "metadata": {"imported_id": "def"}},
        {"id": c_id, "type": "normatif_position", "metadata": {"imported_id": "c"}},
    ]
    schemes_c = [
        {
            "id": inf_id,
            "scheme": "inference",
            "premises": [str(def_id)],
            "conclusion": str(c_id),
        }
    ]
    violations_c = check_hume(nodes_c, schemes_c, edges_a)
    assert len(violations_c) == 1

    # Case D: conclusion descriptive = 0 violations
    nodes_d = [
        {"id": p1_id, "type": "descriptif", "metadata": {"imported_id": "p1"}},
        {"id": c_id, "type": "descriptif", "metadata": {"imported_id": "c"}},
    ]
    schemes_d = [
        {
            "id": inf_id,
            "scheme": "inference",
            "premises": [str(p1_id)],
            "conclusion": str(c_id),
        }
    ]
    violations_d = check_hume(nodes_d, schemes_d, edges_a)
    assert len(violations_d) == 0


async def test_import_hume_violations_blocking():
    test_engine = create_async_engine(DATABASE_URL, echo=False)
    test_session_local = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )

    async def override_get_db():
        async with test_session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Clean up DB
    async with test_session_local() as session:
        from sqlalchemy import delete

        from src.models import CausalEdge

        await session.execute(delete(CausalEdge))
        await session.execute(delete(Edge))
        await session.execute(delete(SchemeNode))
        await session.execute(delete(Node))
        await session.commit()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            p_id = str(uuid.uuid4())
            c_id = str(uuid.uuid4())
            inf_id = str(uuid.uuid4())

            violating_payload = {
                "nodes": [
                    {
                        "id": p_id,
                        "type": "descriptif",
                        "domain": "test",
                        "text": "Prémisse descriptive P",
                        "tier": "moyen",
                        "confidence": 0.6,
                    },
                    {
                        "id": c_id,
                        "type": "normatif_conclusion",
                        "domain": "test",
                        "text": "Conclusion normative C",
                        "tier": "moyen",
                        "confidence": 0.6,
                    },
                ],
                "scheme_nodes": [
                    {
                        "id": inf_id,
                        "scheme": "inference",
                        "premises": [p_id],
                        "conclusion": c_id,
                        "strength": "defaisable_faible",
                    }
                ],
            }

            # 1. Post to /import without allow_hume_violations -> Expect 422
            res1 = await client.post("/import", json=violating_payload)
            assert res1.status_code == 422
            data1 = res1.json()
            assert data1["detail"] == "hume_violations"
            assert len(data1["violations"]) == 1
            assert data1["violations"][0]["scheme_id"] == inf_id

            # Verify that NOTHING was saved to the database
            async with test_session_local() as session:
                cnt_nodes = (await session.execute(select(Node))).scalars().all()
                assert len(cnt_nodes) == 0

            # 2. Post to /import with allow_hume_violations=true -> Expect 200 and warning
            res2 = await client.post(
                "/import?allow_hume_violations=true", json=violating_payload
            )
            assert res2.status_code == 200
            data2 = res2.json()
            assert "warnings" in data2
            assert len(data2["warnings"]["hume_violations"]) == 1

            # Verify that it was saved to the database
            async with test_session_local() as session:
                cnt_nodes = (await session.execute(select(Node))).scalars().all()
                assert len(cnt_nodes) == 2

    finally:
        app.dependency_overrides.clear()
        await test_engine.dispose()


async def test_validate_hume_on_seed():
    test_engine = create_async_engine(DATABASE_URL, echo=False)
    test_session_local = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )

    async def override_get_db():
        async with test_session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with test_session_local() as session:
        await seed(session)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/validate/hume")
            assert res.status_code == 200
            data = res.json()
            # The seed determinism graph has explicit normatif bridges, so violations count must be 0
            assert data["count"] == 0
            assert len(data["violations"]) == 0
    finally:
        app.dependency_overrides.clear()
        await test_engine.dispose()
