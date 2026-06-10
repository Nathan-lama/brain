import asyncio
import sys
from sqlalchemy import select

sys.path.insert(0, r"c:\Users\natbo\Documents\buildandburn\brain\backend")
from src.database import AsyncSessionLocal
from src.models import Node, SchemeNode, Edge

async def main():
    async with AsyncSessionLocal() as session:
        # Fetch all nodes
        nodes_res = await session.execute(select(Node))
        nodes = nodes_res.scalars().all()
        print("=== NODES ===")
        for n in nodes:
            print(f"Node ID: {n.id}, Type: {n.type}, Domain: {n.domain}, Text: {n.text}, Tier: {n.tier}, Weight: {n.weight}")

        # Fetch all schemes
        schemes_res = await session.execute(select(SchemeNode))
        schemes = schemes_res.scalars().all()
        print("\n=== SCHEMES ===")
        for s in schemes:
            print(f"Scheme ID: {s.id}, Scheme: {s.scheme}, Weight: {s.weight}, Metadata: {s.metadata_}")

if __name__ == "__main__":
    asyncio.run(main())
