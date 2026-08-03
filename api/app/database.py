import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "POSTGRES_URI",
    "postgresql+asyncpg://forge_user:forge_password@localhost:5432/forge_db",
)

# --------------------------------------------------------------------------- #
# Engine configuration
# --------------------------------------------------------------------------- #
# pool_size=5 keeps a small connection pool suitable for local dev.
# echo=True logs every SQL statement — invaluable while learning, disable in prod.
engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    pool_size=5,
    max_overflow=10,
)

# --------------------------------------------------------------------------- #
# Session factory
# --------------------------------------------------------------------------- #
# expire_on_commit=False prevents SQLAlchemy from lazily-expiring attributes
# after a commit, which would cause "greenlet" errors in async code when you
# try to access a column value after the session is committed.
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    """FastAPI dependency that yields an async database session.

    Usage in a route:
        @router.post("/jobs")
        async def create_job(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
