import asyncio
import os
import sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, r"c:\Users\natbo\Documents\buildandburn\brain\backend")
from src.database import DATABASE_URL, Base
from src.models import Node, Edge, SchemeNode, CausalEdge

async def main():
    # Make sure we use the postgres base URL to check/create the DB
    base_url, db_name = DATABASE_URL.rsplit("/", 1)
    if "second_brain" in db_name:
        test_db_name = "second_brain_test"
    else:
        test_db_name = db_name + "_test"

    postgres_url = base_url + "/postgres"
    print(f"Connecting to {postgres_url} to check/create {test_db_name}")
    
    # Connect using asyncpg
    engine_postgres = create_async_engine(postgres_url, isolation_level="AUTOCOMMIT")
    async with engine_postgres.connect() as conn:
        result = await conn.execute(
            text(f"SELECT 1 FROM pg_database WHERE datname='{test_db_name}'")
        )
        exists = result.scalar() is not None
        if not exists:
            print(f"Database {test_db_name} does not exist. Creating...")
            await conn.execute(text(f"CREATE DATABASE {test_db_name}"))
            print("Database created!")
        else:
            print(f"Database {test_db_name} already exists.")
    await engine_postgres.dispose()

    # Now connect to test_db_name and create tables
    test_db_url = base_url + "/" + test_db_name
    print(f"Connecting to {test_db_url} to create tables")
    engine_test = create_async_engine(test_db_url)
    async with engine_test.begin() as conn:
        # Enable pgvector extension first
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        print("Tables created successfully!")
    await engine_test.dispose()

if __name__ == "__main__":
    asyncio.run(main())
