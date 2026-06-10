import asyncio

from sqlalchemy import select

from seed_determinism import IDS
from src.database import AsyncSessionLocal
from src.models import Node


async def main():
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Node))
        nodes = res.scalars().all()

        print(f"Found {len(nodes)} nodes to update embeddings for.")

        for n in nodes:
            emb = [0.0] * 768
            if n.id == IDS["d1"]:
                emb[0] = 1.0
                print(f"Setting embedding for d1: {n.text[:20]}...")
            elif n.id == IDS["d2"]:
                emb[0] = 0.95
                emb[1] = 0.05
                print(f"Setting embedding for d2: {n.text[:20]}...")
            elif n.id == IDS["b1"]:
                emb[0] = 0.70
                emb[1] = 0.30
                print(f"Setting embedding for b1: {n.text[:20]}...")
            elif n.id == IDS["c1"]:
                emb[0] = 0.60
                emb[1] = 0.40
                print(f"Setting embedding for c1: {n.text[:20]}...")
            else:  # p1
                emb[0] = -0.5
                emb[1] = 0.866
                print(f"Setting embedding for p1: {n.text[:20]}...")
            n.embedding = emb

        await session.commit()
        print("Successfully updated database with synthetic embeddings!")


if __name__ == "__main__":
    asyncio.run(main())
