import asyncio
import json

from src.database import AsyncSessionLocal
from src.services.extraction import extract_pipeline


async def main():
    async with AsyncSessionLocal() as db:
        print("Starting LLM extraction pipeline...")
        result = await extract_pipeline(
            text="Je crois au déterminisme mais je défends la méritocratie",
            db=db,
            k_neighbors=5,
        )
        print("LLM extraction completed successfully!")

        # Serialize result to JSON and print
        payload = result.model_dump(mode="json", by_alias=True)
        print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
