"""
Redis Sorted Set priority queue for job scheduling.

Design decision: Sorted Set (ZADD / ZPOPMIN) over Lists or Streams
═══════════════════════════════════════════════════════════════════

We chose a Redis Sorted Set because priority is a first-class requirement.

ALTERNATIVE 1 — Multiple Lists (one per priority level):
  Workers would BRPOP from "queue:high" first, then fall back to "queue:normal".
  This works for a small, fixed number of priority tiers (e.g. high/normal/low)
  but becomes unwieldy with arbitrary numeric priorities (0-100 = 101 lists).
  It also introduces starvation risk: a steady stream of high-priority jobs
  would prevent normal-priority jobs from ever executing.

ALTERNATIVE 2 — Redis Streams (XADD / XREADGROUP):
  Streams provide built-in consumer groups with message acknowledgement,
  pending entry tracking, and auto-redelivery — powerful for multi-consumer
  scenarios. However, Streams have no native concept of priority. We'd need
  separate streams per priority level (same proliferation problem as Lists)
  or a secondary sorting mechanism. The consumer-group machinery also adds
  complexity (XACK, XCLAIM, XPENDING, XAUTOCLAIM) that we'd need to learn
  before we actually need it.

OUR CHOICE — Sorted Set:
  A single data structure handles arbitrary numeric priority. ZPOPMIN is
  atomic (no double-delivery). The score encodes both priority and timestamp,
  giving us "highest priority first, FIFO within same priority."

  What we give up: no built-in consumer groups or message acknowledgement.
  We'll implement equivalent crash-recovery semantics in Phase 3 using a
  "processing set" pattern (move the job ID to a second sorted set with a
  deadline score; if the deadline passes without completion, a sweeper
  re-enqueues the job).

Score encoding
──────────────
  score = -priority × 1_000_000_000_000 + unix_timestamp_ms

  • Higher priority → more negative score → popped first by ZPOPMIN.
  • Within same priority → lower timestamp (earlier) → popped first (FIFO).

Example:
  priority=10, time=1700000000000ms → score = -10_000_000_000_000 + 1_700_000_000_000 = -8_300_000_000_000
  priority=0,  time=1700000000000ms → score =                  0 + 1_700_000_000_000 =  1_700_000_000_000
  The priority=10 job has a lower score and gets popped first. ✓
"""

import time
import logging
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis

logger = logging.getLogger("forge.queue")

# Redis key for the main job queue
QUEUE_KEY = "forge:queue:jobs"

# Key for the processing set (jobs currently being worked on).
# Used in Phase 3 for crash recovery — defined here for forward compatibility.
PROCESSING_KEY = "forge:queue:processing"


def _compute_score(priority: int, run_after: Optional[datetime] = None) -> float:
    """
    Compute the Sorted Set score for a job.

    The score must satisfy two ordering requirements:
    1. Higher priority jobs should be dequeued before lower priority jobs.
    2. Within the same priority, jobs should be dequeued in FIFO order.

    We achieve this by encoding priority in the "trillions" place (negated)
    and the timestamp in the "ones" place (milliseconds since epoch).
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
    Add a job ID to the priority queue.

    Returns True if the job was added (new), False if it already existed
    in the queue (ZADD NX behaviour).
    """
    score = _compute_score(priority, run_after)
    # NX=True: only add if the member doesn't already exist.
    # This prevents re-enqueuing a job that's already in the queue
    # (e.g. from a duplicate POST /jobs request).
    added = await redis.zadd(QUEUE_KEY, {job_id: score}, nx=True)
    logger.info(
        f"Enqueued job {job_id} with priority={priority} score={score} "
        f"(new={bool(added)})"
    )
    return bool(added)


async def dequeue_job(redis: aioredis.Redis) -> Optional[str]:
    """
    Atomically pop the highest-priority (lowest score) job from the queue.

    Returns the job ID string, or None if the queue is empty.

    Note: In Phase 3, this will be extended to move the job into the
    PROCESSING_KEY sorted set with a deadline score for crash recovery.
    """
    # ZPOPMIN returns a list of (member, score) tuples, or empty list.
    result = await redis.zpopmin(QUEUE_KEY, count=1)
    if not result:
        return None

    job_id, score = result[0]
    logger.info(f"Dequeued job {job_id} (score={score})")
    return job_id


async def get_queue_depth(redis: aioredis.Redis) -> int:
    """Return the number of jobs currently waiting in the queue."""
    return await redis.zcard(QUEUE_KEY)


async def peek_queue(
    redis: aioredis.Redis, count: int = 10
) -> list[tuple[str, float]]:
    """
    Peek at the top N jobs in the queue without removing them.
    Returns list of (job_id, score) tuples, ordered by priority.
    Useful for debugging and dashboard display.
    """
    return await redis.zrange(QUEUE_KEY, 0, count - 1, withscores=True)
