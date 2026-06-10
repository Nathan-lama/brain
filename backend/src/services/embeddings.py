import os

import httpx

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")


async def get_embeddings(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={
                "model": EMBED_MODEL,
                "input": texts,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["embeddings"]
