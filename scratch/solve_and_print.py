import asyncio
from src.database import AsyncSessionLocal
from src.services.solver import CoherenceSolverService

async def main():
    async with AsyncSessionLocal() as session:
        res = await CoherenceSolverService.solve(session)
        print("Solve Result:")
        import json
        # convert uuid to str for printing
        def default_serializer(obj):
            import uuid
            if isinstance(obj, uuid.UUID):
                return str(obj)
            raise TypeError("Type not serializable")
        print(json.dumps(res, indent=2, default=default_serializer))

if __name__ == "__main__":
    asyncio.run(main())
