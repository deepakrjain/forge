"""
Two-tier read-through cache for job lookups.

Architecture
════════════
  In-Memory (TTL: 2s)  →  Redis (TTL: 10s)  →  Postgres (source of truth)

Read path (get_cached_job):
  1. Check in-memory dict. If hit and not expired, return immediately.
  2. Check Redis key `forge:job:{id}`. If hit, backfill in-memory, return.
  3. Fall through to Postgres (caller handles this).

Write path (invalidate_job_cache):
  On any status change, delete from both tiers.

Invalidation strategy: Write-Through Deletion
══════════════════════════════════════════════
We chose DELETE-on-write over SET-on-write (updating the cache with new data):

  • Idempotent: DEL is safe to call multiple times, from multiple processes.
  • Avoids stale-write races: if two status updates arrive out of order,
    DEL ensures the next read fetches fresh data from Postgres. A SET could
    overwrite newer data with older data if the updates were reordered.
  • Simpler: we don't need to serialize the full updated Job object at
    invalidation time — we just delete the key and let the next read
    repopulate.

Multi-instance behaviour:
  The in-memory tier is per-process. When API instance A invalidates,
  instance B's in-memory cache may still serve stale data for up to 2
  seconds. The Redis tier handles cross-instance consistency. This is
  an explicit availability-over-consistency tradeoff — acceptable for
  a dashboard polling every 1-3 seconds.

  In a production system with stricter consistency requirements, you'd
  use Redis Pub/Sub to broadcast invalidation events to all API instances,
  or skip the in-memory tier entirely and rely only on Redis.
"""

import json
import time
import logging
from typing import Any, Dict, Optional

import redis.asyncio as aioredis

logger = logging.getLogger("forge.cache")

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
MEMORY_TTL_SECONDS = 2    # In-memory cache lifespan
REDIS_TTL_SECONDS = 10    # Redis cache lifespan
CACHE_KEY_PREFIX = "forge:job:"

# --------------------------------------------------------------------------- #
# In-memory cache (process-local)
# --------------------------------------------------------------------------- #
# Structure: { job_id_str: (data_dict, expiry_timestamp) }
_memory_cache: Dict[str, tuple[Dict[str, Any], float]] = {}


def _memory_get(job_id: str) -> Optional[Dict[str, Any]]:
    """Check in-memory cache. Returns cached dict or None if miss/expired."""
    entry = _memory_cache.get(job_id)
    if entry is None:
        return None
    data, expiry = entry
    if time.time() > expiry:
        # Expired — remove lazily
        del _memory_cache[job_id]
        return None
    return data


def _memory_set(job_id: str, data: Dict[str, Any]) -> None:
    """Store a job dict in the in-memory cache with TTL."""
    _memory_cache[job_id] = (data, time.time() + MEMORY_TTL_SECONDS)


def _memory_delete(job_id: str) -> None:
    """Remove a job from the in-memory cache."""
    _memory_cache.pop(job_id, None)


# --------------------------------------------------------------------------- #
# Redis cache helpers
# --------------------------------------------------------------------------- #
def _redis_key(job_id: str) -> str:
    return f"{CACHE_KEY_PREFIX}{job_id}"


async def _redis_get(redis: aioredis.Redis, job_id: str) -> Optional[Dict[str, Any]]:
    """Check Redis cache. Returns cached dict or None."""
    raw = await redis.get(_redis_key(job_id))
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        # Corrupted cache entry — treat as miss
        await redis.delete(_redis_key(job_id))
        return None


async def _redis_set(
    redis: aioredis.Redis, job_id: str, data: Dict[str, Any]
) -> None:
    """Store a job dict in Redis with TTL."""
    await redis.set(
        _redis_key(job_id),
        json.dumps(data, default=str),  # default=str handles datetime, UUID
        ex=REDIS_TTL_SECONDS,
    )


async def _redis_delete(redis: aioredis.Redis, job_id: str) -> None:
    """Remove a job from Redis cache."""
    await redis.delete(_redis_key(job_id))


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
async def get_cached_job(
    redis: aioredis.Redis, job_id: str
) -> Optional[Dict[str, Any]]:
    """
    Attempt to read a job from the cache tiers.

    Returns:
        - The cached job dict if found in either tier (and backfills
          the in-memory tier on a Redis hit).
        - None if the job is not cached anywhere (caller should query Postgres
          and then call set_cached_job to populate both tiers).
    """
    # Tier 1: in-memory
    data = _memory_get(job_id)
    if data is not None:
        logger.debug(f"Cache HIT (memory) for job {job_id}")
        return data

    # Tier 2: Redis
    data = await _redis_get(redis, job_id)
    if data is not None:
        logger.debug(f"Cache HIT (redis) for job {job_id}")
        # Backfill in-memory for subsequent requests in this process
        _memory_set(job_id, data)
        return data

    logger.debug(f"Cache MISS for job {job_id}")
    return None


async def set_cached_job(
    redis: aioredis.Redis, job_id: str, data: Dict[str, Any]
) -> None:
    """
    Populate both cache tiers after a Postgres read.

    Called by the GET /jobs/:id handler when the cache missed and we
    had to go to Postgres.
    """
    _memory_set(job_id, data)
    await _redis_set(redis, job_id, data)
    logger.debug(f"Cache SET (both tiers) for job {job_id}")


async def invalidate_job_cache(
    redis: aioredis.Redis, job_id: str
) -> None:
    """
    Invalidate a job from both cache tiers.

    Called on any status change (job creation, worker status updates).
    Uses DELETE (not SET) — see module docstring for rationale.
    """
    _memory_delete(job_id)
    await _redis_delete(redis, job_id)
    logger.debug(f"Cache INVALIDATED for job {job_id}")
