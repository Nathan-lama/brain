from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database import DATABASE_URL, get_db
from src.main import app
from src.models import Node, NodeType
from src.services.llm import (
    ClaimsExtractionResponse,
    ExtractedClaim,
    RelationExtractionResponse,
    RelationItem,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class MockLLMClient:
    async def extract_claims(self, text: str) -> ClaimsExtractionResponse:
        return ClaimsExtractionResponse(
            raisonnement="Décomposition de la phrase sur le déterminisme et la méritocratie.",
            claims=[
                ExtractedClaim(
                    raisonnement="Claim descriptif sur la croyance au déterminisme.",
                    temp_id="claim_1",
                    type=NodeType.DESCRIPTIF,
                    domain="metaphysique",
                    text="Je crois au déterminisme.",
                    tier="certain",
                ),
                ExtractedClaim(
                    raisonnement="Claim normatif sur la défense de la méritocratie.",
                    temp_id="claim_2",
                    type=NodeType.NORMATIF_POSITION,
                    domain="politique",
                    text="Je défends la méritocratie.",
                    tier="fort",
                ),
            ],
        )

    async def extract_relations(
        self, new_claims: list[dict], existing_claims: list[dict]
    ) -> RelationExtractionResponse:
        return RelationExtractionResponse(
            raisonnement="Analyse de la contradiction logique de la coexistence du mérite et du déterminisme.",
            relations=[
                RelationItem(
                    raisonnement="Le déterminisme exclut le libre arbitre, contredisant la base de la méritocratie.",
                    relation_type="contredit",
                    source_id="claim_1",
                    target_id="claim_2",
                    bridge_text="Le mérite requiert une origination ultime (libre arbitre).",
                    bridge_domain="ethique",
                )
            ],
        )


async def test_extract_endpoint_dry_run():
    test_engine = create_async_engine(DATABASE_URL, echo=False)
    test_session_local = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )

    async def override_get_db():
        async with test_session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async def mock_get_embeddings(texts: list[str]) -> list[list[float]]:
        return [[0.1] * 768 for _ in texts]

    # Patch LLMClient and get_embeddings in extraction service and main
    with (
        patch("src.services.extraction.LLMClient", return_value=MockLLMClient()),
        patch(
            "src.services.extraction.get_embeddings", side_effect=mock_get_embeddings
        ),
        patch("src.main.get_embeddings", side_effect=mock_get_embeddings),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Test Dry Run (dry_run=true)
            response = await client.post(
                "/extract?dry_run=true",
                json={
                    "text": "Je crois au déterminisme mais je défends la méritocratie"
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert "nodes" in data
            assert "scheme_nodes" in data

            nodes = data["nodes"]
            assert len(nodes) == 3

            types = [n["type"] for n in nodes]
            assert "descriptif" in types
            assert "normatif_position" in types
            assert "pont_normatif" in types

            scheme_nodes = data["scheme_nodes"]
            schemes = [s["scheme"] for s in scheme_nodes]
            assert "conflit" in schemes
            assert "inference" in schemes

            # Verify the dry run did not write to the live nodes table
            async with test_session_local() as session:
                res = await session.execute(
                    select(Node).filter(Node.text == "Je crois au déterminisme.")
                )
                node = res.scalar_one_or_none()
                assert node is None

            # 2. Test Live Import (dry_run=false)
            response_live = await client.post(
                "/extract?dry_run=false",
                json={
                    "text": "Je crois au déterminisme mais je défends la méritocratie"
                },
            )
            assert response_live.status_code == 200
            live_data = response_live.json()
            assert live_data["nodes_created"] >= 2

            # Verify the node was written to database
            async with test_session_local() as session:
                res = await session.execute(
                    select(Node).filter(Node.text == "Je crois au déterminisme.")
                )
                node = res.scalar_one_or_none()
                assert node is not None
                assert node.type == NodeType.DESCRIPTIF

    app.dependency_overrides.clear()
    await test_engine.dispose()


def test_llm_client_provider_config_switching(monkeypatch):
    from src.services.llm import LLMClient

    # 1. Test Ollama default configuration via environment
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    client_ollama = LLMClient()
    assert client_ollama.provider == "ollama"
    assert client_ollama.base_url == "http://localhost:11434/v1"
    assert client_ollama.api_key == "ollama"

    # 2. Test OpenAI compatible configuration via environment
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_BASE_URL", "https://custom-openai-api.com/v1")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("LLM_API_KEY", "secret-api-key")

    client_openai = LLMClient()
    assert client_openai.provider == "openai_compatible"
    assert client_openai.base_url == "https://custom-openai-api.com/v1"
    assert client_openai.model == "gpt-4o"
    assert client_openai.api_key == "secret-api-key"
