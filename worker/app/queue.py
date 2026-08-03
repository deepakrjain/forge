"""
Worker Redis Queue Helper Module.

Provides queue scheduling, delayed job promotion, and DLQ operations for the worker process.
"""

import time
import logging
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis

logger = logging.getLogger("forge.worker.queue")

QUEUE_KEY = "forge:queue:jobs"
DELAYED_KEY = "forge:queue:delayed"
DLQ_KEY = "forge:queue:dlq"
PROCESSING_KEY = "forge:queue:processing"

# Lua script to promote matured delayed jobs to the ready queue
PROMOTE_LUA_SCRIPT = """
local delayed_key = KEYS[1]
local queue_key = KEYS[2]
local now_ms = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])

local items = redis.call('ZRANGEBYSCORE', delayed_key, '-inf', now_ms, 'LIMIT', 0, limit)
local promoted_count = 0

for _, job_id in ipairs(items) do
    redis.call('ZREM', delayed_key, job_id)
    local ready_score = tonumber(now_ms)
    redis.call('ZADD', queue_key, 'NX', ready_score, job_id)
    promoted_count = promoted_count + 1
end

return promoted_count
"""


def _compute_score(priority: int, run_after: Optional[datetime] = None) -> float:
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
    """Enqueue a job into ready queue or delayed queue."""
    now = datetime.now(timezone.utc)
    if run_after is not None and run_after > now:
        delayed_score = float(int(run_after.timestamp() * 1000))
        added = await redis.zadd(DELAYED_KEY, {job_id: delayed_score}, nx=True)
        logger.info(f"Worker scheduled delayed job {job_id} run_after={run_after.isoformat()}")
        return bool(added)

    score = _compute_score(priority, run_after)
    added = await redis.zadd(QUEUE_KEY, {job_id: score}, nx=True)
    logger.info(f"Worker enqueued job {job_id} priority={priority}")
    return bool(added)


async def promote_delayed_jobs(redis: aioredis.Redis, limit: int = 100) -> int:
    """Promote matured jobs from DELAYED_KEY to QUEUE_KEY."""
    now_ms = int(time.time() * 1000)
    try:
        promoted = await redis.eval(PROMOTE_LUA_SCRIPT, 2, DELAYED_KEY, QUEUE_KEY, now_ms, limit)
        if promoted > 0:
            logger.info(f"Promoted {promoted} delayed job(s) to ready queue")
        return int(promoted)
    except Exception as e:
        logger.error(f"Error promoting delayed jobs in worker: {e}")
        return 0


async def push_to_dlq(redis: aioredis.Redis, job_id: str) -> bool:
    """Move job to Dead Letter Queue (DLQ)."""
    now_ms = int(time.time() * 1000)
    async with redis.pipeline(transaction=True) as pipe:
        pipe.zrem(QUEUE_KEY, job_id)
        pipe.zrem(DELAYED_KEY, job_id)
        pipe.zrem(PROCESSING_KEY, job_id)
        pipe.zadd(DLQ_KEY, {job_id: now_ms})
        res = await pipe.execute()
    logger.info(f"Worker moved job {job_id} to DLQ ({DLQ_KEY})")
    return bool(res[-1])
