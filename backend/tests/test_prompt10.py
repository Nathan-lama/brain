import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from seed_determinism import IDS, seed
from src.database import DATABASE_URL, get_db
from src.main import app
from src.models import Domain, Node

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_prompt10_domains_and_exports():
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
        # Seed default domains manually
        for name in [
            "justice",
            "économie",
            "santé",
            "éducation",
            "environnement",
            "institutions",
            "climat",
            "ethique",
            "politique",
            "général",
        ]:
            res_exist = await session.execute(
                select(Domain).filter(Domain.name == name)
            )
            if not res_exist.scalar_one_or_none():
                session.add(Domain(name=name))
        await session.commit()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Test GET /domains (should include default seed domains like climat)
            res_domains = await client.get("/domains")
            assert res_domains.status_code == 200
            domains_list = res_domains.json()
            assert len(domains_list) >= 1

            # 2. Test POST /domains
            new_domain_payload = {"name": "test_domain_philosophy", "parent_id": None}
            res_create = await client.post("/domains", json=new_domain_payload)
            assert res_create.status_code == 200
            created_dom = res_create.json()
            assert created_dom["name"] == "test_domain_philosophy"
            dom_id = created_dom["id"]

            # 3. Tag a node with this domain and update domain name to test cascade
            async with test_session_local() as session:
                res_node = await session.execute(
                    select(Node).filter(Node.id == IDS["d1"])
                )
                node = res_node.scalar_one()
                node.domain = "test_domain_philosophy"
                await session.commit()

            # Update domain name
            update_payload = {"name": "test_domain_metaphysics", "parent_id": None}
            res_update = await client.put(f"/domains/{dom_id}", json=update_payload)
            assert res_update.status_code == 200

            # Verify that node domain is updated to test_domain_metaphysics
            async with test_session_local() as session:
                res_node = await session.execute(
                    select(Node).filter(Node.id == IDS["d1"])
                )
                node = res_node.scalar_one()
                assert node.domain == "test_domain_metaphysics"

            # 4. Test DELETE /domains/{id}
            res_delete = await client.delete(f"/domains/{dom_id}")
            assert res_delete.status_code == 200

            # Verify that the node domain falls back to general/général
            async with test_session_local() as session:
                res_node = await session.execute(
                    select(Node).filter(Node.id == IDS["d1"])
                )
                node = res_node.scalar_one()
                assert node.domain == "général"

            # 5. Test Exports
            res_aif = await client.get("/export/aif")
            assert res_aif.status_code == 200
            aif_data = res_aif.json()
            assert "nodes" in aif_data
            assert "edges" in aif_data

            # Test AIF import roundtrip
            res_import_aif = await client.post("/import/aif", json=aif_data)
            assert res_import_aif.status_code == 200
            assert res_import_aif.json()["status"] == "ok"

            # SADFace Export
            res_sad = await client.get("/export/sadface")
            assert res_sad.status_code == 200
            sad_data = res_sad.json()
            assert "nodes" in sad_data
            assert "edges" in sad_data

            # SADFace Import
            res_import_sad = await client.post("/import/sadface", json=sad_data)
            assert res_import_sad.status_code == 200
            assert res_import_sad.json()["status"] == "ok"

            # GraphML Export
            res_graphml = await client.get("/export/graphml")
            assert res_graphml.status_code == 200
            assert "xml" in res_graphml.headers["content-type"]

            # DOT Export
            res_dot = await client.get("/export/dot")
            assert res_dot.status_code == 200
            assert "plain" in res_dot.headers["content-type"]

            # 6. Test Note Generator
            note_payload = {"domain": "politique", "node_id": None}
            res_note = await client.post("/notes/generate", json=note_payload)
            assert res_note.status_code == 200
            assert "note" in res_note.json()

    finally:
        app.dependency_overrides.clear()
        await test_engine.dispose()


async def test_prompt10_sensitivity():
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
        from sqlalchemy import update

        from src.models import SchemeNode, TierKind

        await session.execute(
            update(Node)
            .where(Node.id.in_([IDS["p1"], IDS["c1"]]))
            .values(tier=TierKind.MOYEN, weight=0.6)
        )
        await session.execute(
            update(SchemeNode).where(SchemeNode.id == IDS["ra1"]).values(weight=0.1)
        )
        await session.commit()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Test sensitivity endpoint
            res = await client.get("/solve/sensitivity")
            assert res.status_code == 200
            data = res.json()
            assert "claims" in data
            assert "tensions" in data

            p1_id_str = str(IDS["p1"])
            c1_id_str = str(IDS["c1"])

            # Find tension of type conflit_direct involving p1 and c1
            t_conflict = None
            for t in data["tensions"]:
                if (
                    "explanation" in t
                    and p1_id_str in t["explanation"]
                    and c1_id_str in t["explanation"]
                ):
                    t_conflict = t
                    break

            assert t_conflict is not None, (
                "Conflict tension p1 VS c1 not found in sensitivity output"
            )
            assert t_conflict["robustesse"] == "fragile"
            assert "cède" in t_conflict["explanation"]

            # Verify the claim sensitivity for p1
            p1_sens = None
            for c in data["claims"]:
                if c["claim_id"] == p1_id_str:
                    p1_sens = c
                    break
            assert p1_sens is not None
            assert p1_sens["verdict"] == "rejected"
            assert p1_sens["robustesse"] == "fragile"
            assert p1_sens["flip_delta"] == 1
            assert p1_sens["flip_tier"] == "fort"

    finally:
        app.dependency_overrides.clear()
        await test_engine.dispose()
