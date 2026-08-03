"""
Async Redis connection pool and lifecycle management.

Uses redis.asyncio (formerly aioredis) with the optional hiredis C parser
for faster protocol parsing. The connection pool is created once at app
startup and shared across all request handlers via FastAPI dependency
injection.
"""

import os
import logging

import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("forge.redis")

REDIS_URL = os.getenv("REDIS_URI", "redis://localhost:6379/0")

# --------------------------------------------------------------------------- #
# Global connection pool
# --------------------------------------------------------------------------- #
# We initialise this as None and create the actual pool in init_redis().
# This avoids opening connections at import time (which would break tests
# and cause issues if Redis isn't running when the module is first imported).
_redis_pool: aioredis.Redis | None = None


async def init_redis() -> aioredis.Redis:
    """Create the global Redis connection pool. Call once during app startup."""
    global _redis_pool
    _redis_pool = aioredis.from_url(
        REDIS_URL,
        decode_responses=True,  # return str instead of bytes
        max_connections=20,
    )
    # Verify connectivity
    await _redis_pool.ping()
    logger.info(f"Redis connected: {REDIS_URL}")
    return _redis_pool


async def close_redis() -> None:
    """Gracefully close the Redis connection pool. Call during app shutdown."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None
        logger.info("Redis connection pool closed.")


async def get_redis() -> aioredis.Redis:
    """FastAPI dependency that provides the shared Redis client.

    Usage in a route:
        @router.post("/jobs")
        async def create_job(redis: aioredis.Redis = Depends(get_redis)):
            ...
    """
    if _redis_pool is None:
        raise RuntimeError(
            "Redis pool not initialised. Was init_redis() called during startup?"
        )
    return _redis_pool
