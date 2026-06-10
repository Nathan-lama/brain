import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath("backend"))

from sqlalchemy import select
from src.database import AsyncSessionLocal
from src.models import SchemeNode, SchemeType

async def query_weights():
    async with AsyncSessionLocal() as session:
        stmt = select(SchemeNode.weight).where(SchemeNode.scheme == SchemeType.INFERENCE).distinct()
        res = await session.execute(stmt)
        rows = res.scalars().all()
        print("DISTINCT inference weights:")
        for w in rows:
            print(w)

if __name__ == "__main__":
    asyncio.run(query_weights())
