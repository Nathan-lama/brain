import os
import sys

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

# Load environment variables from root directory .env
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../../.env"))
load_dotenv()  # Fallback to local .env

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/second_brain"
)

# Format for asyncpg
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

# Check if we are running in tests (pytest)
IS_TESTING = "pytest" in sys.modules or os.getenv("TESTING") == "1"

if IS_TESTING:
    if "second_brain" in DATABASE_URL and "second_brain_test" not in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("second_brain", "second_brain_test")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)
Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
