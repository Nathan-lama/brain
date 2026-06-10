import sys

sys.path.insert(0, r"c:\Users\natbo\Documents\buildandburn\brain\backend")

import asyncio

from src.database import AsyncSessionLocal
from src.services.solver import CoherenceSolverService


async def main():
    async with AsyncSessionLocal() as session:
        res = await CoherenceSolverService.solve(session)
        print("--- VIOLATED TENSIONS IN BASELINE ---")
        for v in res["violated"]:
            print(f"Type: {v.type}")
            print(f"  Scheme ID: {v.scheme_id}")
            print(f"  Poids: {v.poids}")
            print(f"  Claims: {[c.text[:40] for c in v.claims]}")


if __name__ == "__main__":
    asyncio.run(main())
