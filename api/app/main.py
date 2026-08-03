import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select, text

from app.database import engine, async_session
from app.models_db import Base, APIKey
from app.redis import init_redis, close_redis
from app.routes.jobs import router as jobs_router
from app.routes.dlq import router as dlq_router
from forge_shared import JobStatus

logger = logging.getLogger("forge.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    On startup:
      1. Creates all Postgres tables (dev convenience — use Alembic in prod).
      2. Initialises the Redis connection pool.
      3. Seeds a default developer API key if no keys exist.

    On shutdown:
      1. Closes the Redis connection pool.
      2. Disposes the SQLAlchemy engine.
    """
    # --- Startup ---
    logger.info("Creating database tables (if not exists)...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready.")

    logger.info("Initialising Redis connection pool...")
    await init_redis()

    # Seed default API key for development
    try:
        async with async_session() as session:
            async with session.begin():
                res = await session.execute(select(APIKey).limit(1))
                if not res.scalars().first():
                    dev_key = APIKey(
                        key="forge_dev_key_123",
                        name="Default Developer Key",
                        rate_limit_rpm=60,
                        is_active=True,
                    )
                    session.add(dev_key)
                    logger.info("Seeded default API key: 'forge_dev_key_123' (limit: 60 req/min)")
    except Exception as e:
        logger.warning(f"Skipped API key seeding: {e}")

    yield

    # --- Shutdown ---
    await close_redis()
    await engine.dispose()
    logger.info("All connections closed.")


app = FastAPI(
    title="Forge API",
    description="Distributed Background Job Queue & Worker Platform — REST & WebSocket API",
    version="0.1.0",
    lifespan=lifespan,
)

# --- Register routers ---
app.include_router(jobs_router, prefix="/api")
app.include_router(dlq_router, prefix="/api")


@app.get("/")
def read_root():
    return {
        "service": "Forge API",
        "status": "online",
        "version": "0.1.0",
    }


@app.get("/health")
async def health_check():
    """Liveness probe. Checks both DB and Redis connectivity."""
    # Postgres check
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    # Redis check
    try:
        from app.redis import _redis_pool
        if _redis_pool is not None:
            await _redis_pool.ping()
            redis_status = "connected"
        else:
            redis_status = "not_initialised"
    except Exception:
        redis_status = "disconnected"

    overall = "healthy"
    if db_status != "connected" or redis_status != "connected":
        overall = "degraded"

    return {
        "status": overall,
        "database": db_status,
        "redis": redis_status,
        "job_statuses": [s.value for s in JobStatus],
    }
