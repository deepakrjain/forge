"""
Redis Queue Service for Forge.

Data Structures:
  - QUEUE_KEY = "forge:queue:jobs" (Sorted Set of ready jobs, score = -priority*1e12 + timestamp_ms)
  - DELAYED_KEY = "forge:queue:delayed" (Sorted Set of future jobs, score = run_after_timestamp_ms)
  - DLQ_KEY = "forge:queue:dlq" (Sorted Set of dead-lettered jobs, score = failed_at_timestamp_ms)
  - PROCESSING_KEY = "forge:queue:processing" (Sorted Set of active jobs for crash recovery)
"""

import time
import logging
from datetime import datetime, timezone
from typing import Optional, List, Tuple

import redis.asyncio as aioredis

logger = logging.getLogger("forge.queue")

QUEUE_KEY = "forge:queue:jobs"
DELAYED_KEY = "forge:queue:delayed"
DLQ_KEY = "forge:queue:dlq"
PROCESSING_KEY = "forge:queue:processing"

# Lua script to atomically promote matured jobs from DELAYED_KEY to QUEUE_KEY
PROMOTE_LUA_SCRIPT = """
local delayed_key = KEYS[1]
local queue_key = KEYS[2]
local now_ms = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])

local items = redis.call('ZRANGEBYSCORE', delayed_key, '-inf', now_ms, 'LIMIT', 0, limit)
local promoted_count = 0

for _, job_id in ipairs(items) do
    redis.call('ZREM', delayed_key, job_id)
    -- Add to main ready queue with score based on current time (priority 0 default if not specified)
    local ready_score = tonumber(now_ms)
    redis.call('ZADD', queue_key, 'NX', ready_score, job_id)
    promoted_count = promoted_count + 1
end

return promoted_count
"""


def _compute_score(priority: int, run_after: Optional[datetime] = None) -> float:
    """
    Compute Sorted Set score for ready jobs:
    score = -priority * 1e12 + timestamp_ms
    """
    if run_after is not None:
        ts_ms = int(run_after.timestamp() * 1000)
    else:
        ts_ms = int(time.time() * 1000)

    return -priority * 1_000_000_000_000 + ts_ms


async def enqueue_job(
    redis: aioredis.Redis,
    job_id: str,
    priority: int = 0,
    run_after: Optional[datetime] = None,
) -> bool:
    """
    Enqueue a job. If run_after is in the future, places it into DELAYED_KEY.
    Otherwise, places it directly into QUEUE_KEY.
    """
    now = datetime.now(timezone.utc)
    
    if run_after is not None and run_after > now:
        # Schedule in DELAYED_KEY sorted set
        delayed_score = float(int(run_after.timestamp() * 1000))
        added = await redis.zadd(DELAYED_KEY, {job_id: delayed_score}, nx=True)
        logger.info(
            f"Scheduled delayed job {job_id} in {DELAYED_KEY} "
            f"run_after={run_after.isoformat()} score={delayed_score} (new={bool(added)})"
        )
        return bool(added)

    # Immediate ready queue
    score = _compute_score(priority, run_after)
    added = await redis.zadd(QUEUE_KEY, {job_id: score}, nx=True)
    logger.info(
        f"Enqueued job {job_id} into {QUEUE_KEY} priority={priority} score={score} (new={bool(added)})"
    )
    return bool(added)


async def dequeue_job(redis: aioredis.Redis) -> Optional[str]:
    """Atomically pop the highest-priority job from the ready queue."""
    result = await redis.zpopmin(QUEUE_KEY, count=1)
    if not result:
        return None

    job_id, score = result[0]
    logger.info(f"Dequeued job {job_id} (score={score})")
    return job_id


async def promote_delayed_jobs(redis: aioredis.Redis, limit: int = 100) -> int:
    """
    Promote matured jobs from DELAYED_KEY to QUEUE_KEY whose score <= now_ms.
    Returns the count of promoted jobs.
    """
    now_ms = int(time.time() * 1000)
    try:
        promoted = await redis.eval(PROMOTE_LUA_SCRIPT, 2, DELAYED_KEY, QUEUE_KEY, now_ms, limit)
        if promoted > 0:
            logger.info(f"Promoted {promoted} delayed job(s) to ready queue")
        return int(promoted)
    except Exception as e:
        logger.error(f"Error promoting delayed jobs: {e}")
        return 0


async def push_to_dlq(redis: aioredis.Redis, job_id: str) -> bool:
    """Move job to Dead Letter Queue (DLQ)."""
    now_ms = int(time.time() * 1000)
    # Remove from ready and delayed queues
    async with redis.pipeline(transaction=True) as pipe:
        pipe.zrem(QUEUE_KEY, job_id)
        pipe.zrem(DELAYED_KEY, job_id)
        pipe.zrem(PROCESSING_KEY, job_id)
        pipe.zadd(DLQ_KEY, {job_id: now_ms})
        res = await pipe.execute()
    
    logger.info(f"Moved job {job_id} to DLQ ({DLQ_KEY})")
    return bool(res[-1])


async def remove_from_dlq(redis: aioredis.Redis, job_id: str) -> bool:
    """Remove job from DLQ."""
    removed = await redis.zrem(DLQ_KEY, job_id)
    return bool(removed)


async def get_queue_depth(redis: aioredis.Redis) -> int:
    """Return total number of jobs waiting in ready queue."""
    return await redis.zcard(QUEUE_KEY)

async def remove_job_from_queue(redis: aioredis.Redis, job_id: str) -> bool:
    """Remove a job from all Redis queues (ready, delayed, dlq, processing)."""
    async with redis.pipeline(transaction=True) as pipe:
        pipe.zrem(QUEUE_KEY, job_id)
        pipe.zrem(DELAYED_KEY, job_id)
        pipe.zrem(PROCESSING_KEY, job_id)
        pipe.zrem(DLQ_KEY, job_id)
        res = await pipe.execute()
    return any(res)


async def get_dlq_depth(redis: aioredis.Redis) -> int:
    """Return total number of dead-lettered jobs in DLQ."""
    return await redis.zcard(DLQ_KEY)


async def peek_queue(redis: aioredis.Redis, count: int = 10) -> List[Tuple[str, float]]:
    """Peek top N jobs in ready queue."""
    return await redis.zrange(QUEUE_KEY, 0, count - 1, withscores=True)
