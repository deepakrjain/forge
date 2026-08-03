import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.database import engine
from app.models_db import Base
from app.routes.jobs import router as jobs_router
from forge_shared import JobStatus

logger = logging.getLogger("forge.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    On startup: creates all tables defined in Base.metadata if they don't exist.
    This is convenient for development — in production you'd use Alembic migrations
    to manage schema changes without risking data loss.

    On shutdown: disposes the connection pool gracefully.
    """
    logger.info("Creating database tables (if not exists)...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready.")
    yield
    await engine.dispose()


app = FastAPI(
    title="Forge API",
    description="Distributed Background Job Queue & Worker Platform — REST & WebSocket API",
    version="0.1.0",
    lifespan=lifespan,
)

# --- Register routers ---
app.include_router(jobs_router, prefix="/api")


@app.get("/")
def read_root():
    return {
        "service": "Forge API",
        "status": "online",
        "version": "0.1.0",
    }


@app.get("/health")
async def health_check():
    """Basic liveness probe. Checks DB connectivity."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "job_statuses": [s.value for s in JobStatus],
    }
