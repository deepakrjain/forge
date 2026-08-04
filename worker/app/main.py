"""
Forge Worker Process — Main Entrypoint.

Architecture & Design Overview
═══════════════════════════════

1. Concurrency Model: asyncio.Semaphore(CONCURRENCY)
   The worker uses a single polling loop that pops job IDs from Redis (`ZPOPMIN`).
   New jobs are spawned as asynchronous tasks guarded by an `asyncio.Semaphore`.

2. Real-Time Events (Phase 6):
   - On status changes (`queued` -> `running`, `running` -> `succeeded`/`failed`/`retrying`/`dead`),
     publishes event to Redis Pub/Sub channel `forge:events:jobs`.

3. Exponential Backoff & Retry Logic (Phase 4):
   - On execution failure:
     • If `attempts < max_attempts`: status transitions to `retrying`.
       Calculates `delay = min(base_delay * 2^(attempts - 1), max_delay) + jitter`.
       Schedules the job in `forge:queue:delayed` with `run_after = now() + delay`.
     • If `attempts >= max_attempts`: status transitions to `dead`.
       Pushes the job ID into the Dead Letter Queue (`forge:queue:dlq`).

4. Delayed Job Promotion:
   - Worker continuously runs `promote_delayed_jobs()` to move matured jobs
     (`run_after <= now()`) from `forge:queue:delayed` into `forge:queue:jobs`.

5. Graceful Shutdown (SIGTERM / SIGINT):
   - Signals trigger `shutdown_requested = True`.
   - Polling loop stops dequeuing new work.
   - Active in-flight tasks are given up to 30s to finish before cancellation.
"""

import asyncio
import json
import logging
import random
import signal
import sys
import traceback
from datetime import datetime, timezone, timedelta
from typing import Set, Optional
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy import select, update

from app.config import (
    WORKER_ID,
    POSTGRES_URI,
    REDIS_URI,
    CONCURRENCY,
    POLL_INTERVAL,
)
from app.database import engine, async_session
from app.models_db import Job
from app.handlers import get_handler
from app.queue import enqueue_job, push_to_dlq, promote_delayed_jobs, QUEUE_KEY
from forge_shared import JobStatus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger(f"forge.worker.{WORKER_ID}")

CACHE_PREFIX = "forge:job:"
EVENTS_CHANNEL = "forge:events:jobs"


def compute_backoff_delay(attempts: int, base_delay: float = 2.0, max_delay: float = 3600.0) -> float:
    """
    Compute exponential backoff delay with jitter.
    Formula: min(base_delay * 2^(attempts - 1), max_delay) + random_jitter
    """
    exponential_delay = min(base_delay * (2 ** (attempts - 1)), max_delay)
    jitter = random.uniform(0, 0.5 * exponential_delay)
    return round(exponential_delay + jitter, 2)


async def invalidate_redis_cache(redis_client: aioredis.Redis, job_id: str):
    """Delete cached job representation in Redis on status change."""
    try:
        await redis_client.delete(f"{CACHE_PREFIX}{job_id}")
    except Exception as e:
        logger.warning(f"Failed to invalidate cache for job {job_id}: {e}")


async def publish_job_event(
    redis_client: aioredis.Redis,
    job_id: str,
    old_status: Optional[str],
    new_status: str,
):
    """Publish live event payload to Redis Pub/Sub."""
    event = {
        "job_id": str(job_id),
        "old_status": old_status,
        "new_status": new_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await redis_client.publish(EVENTS_CHANNEL, json.dumps(event))
    except Exception as e:
        logger.warning(f"Failed to publish event for job {job_id}: {e}")


async def process_job(
    job_id_str: str,
    redis_client: aioredis.Redis,
    semaphore: asyncio.Semaphore,
):
    """
    Execute a single job lifecycle inside a concurrency-limited task slot.
    """
    async with semaphore:
        logger.info(f"Starting execution for job {job_id_str}")
        try:
            job_uuid = UUID(job_id_str)
        except ValueError:
            logger.error(f"Invalid UUID format received from queue: {job_id_str}")
            return

        # ------------------------------------------------------------------- #
        # Step 1: Claim job in Postgres (status -> running, attempts += 1)
        # ------------------------------------------------------------------- #
        old_status: Optional[str] = None
        async with async_session() as session:
            async with session.begin():
                result = await session.execute(
                    select(Job).where(Job.id == job_uuid).with_for_update()
                )
                job = result.scalars().first()

                if not job:
                    logger.error(f"Job {job_id_str} popped from Redis but not found in Postgres!")
                    return

                if job.status == JobStatus.CANCELLED.value:
                    logger.info(f"Job {job_id_str} was cancelled prior to execution. Skipping.")
                    return

                old_status = job.status
                job.status = JobStatus.RUNNING.value
                job.attempts += 1
                job.updated_at = datetime.now(timezone.utc)
                
                job_type = job.job_type
                payload = job.payload or {}
                attempts = job.attempts
                max_attempts = job.max_attempts
                priority = job.priority

            # Transaction committed. Invalidate cache and publish live event.
            await invalidate_redis_cache(redis_client, job_id_str)
            await publish_job_event(redis_client, job_id_str, old_status=old_status, new_status="running")

        # ------------------------------------------------------------------- #
        # Step 2: Execute handler
        # ------------------------------------------------------------------- #
        handler = get_handler(job_type)
        job_result: Optional[dict] = None
        error_msg: Optional[str] = None
        execution_success = False

        try:
            logger.info(f"Executing handler for job_type='{job_type}' (id={job_id_str}, attempt {attempts}/{max_attempts})")
            job_result = await handler(payload)
            execution_success = True
            logger.info(f"Job {job_id_str} completed successfully.")
        except Exception as exc:
            execution_success = False
            error_msg = f"{type(exc).__name__}: {str(exc)}\n{traceback.format_exc()}"
            logger.warning(f"Job {job_id_str} failed execution on attempt {attempts}/{max_attempts}: {exc}")

        # ------------------------------------------------------------------- #
        # Step 3: Update final status in Postgres & Queue & PubSub
        # ------------------------------------------------------------------- #
        new_status: str = "failed"
        async with async_session() as session:
            async with session.begin():
                result = await session.execute(
                    select(Job).where(Job.id == job_uuid).with_for_update()
                )
                job = result.scalars().first()

                if job:
                    job.updated_at = datetime.now(timezone.utc)
                    if execution_success:
                        job.status = JobStatus.SUCCEEDED.value
                        job.result = job_result
                        job.error = None
                        new_status = JobStatus.SUCCEEDED.value
                    else:
                        if attempts < max_attempts:
                            # Retrying state with exponential backoff
                            delay_sec = compute_backoff_delay(attempts)
                            run_after = datetime.now(timezone.utc) + timedelta(seconds=delay_sec)
                            job.status = JobStatus.RETRYING.value
                            job.run_after = run_after
                            job.error = error_msg
                            new_status = JobStatus.RETRYING.value
                            
                            # Schedule for future retry
                            await enqueue_job(redis_client, job_id_str, priority=priority, run_after=run_after)
                            logger.info(f"Job {job_id_str} scheduled for retry in {delay_sec}s at {run_after.isoformat()}")
                        else:
                            # Exhausted max attempts -> Move to Dead Letter Queue (DLQ)
                            job.status = JobStatus.DEAD.value
                            job.error = error_msg
                            new_status = JobStatus.DEAD.value
                            
                            await push_to_dlq(redis_client, job_id_str)
                            logger.warning(f"Job {job_id_str} exhausted max attempts ({attempts}/{max_attempts}). Moved to DLQ.")

            # Invalidate cache and publish transition event
            await invalidate_redis_cache(redis_client, job_id_str)
            await publish_job_event(redis_client, job_id_str, old_status="running", new_status=new_status)


async def heartbeat_loop(redis_client: aioredis.Redis, active_tasks: Set[asyncio.Task], started_at_iso: str):
    """Periodically publish worker heartbeat to Redis with 10s TTL."""
    key = f"forge:worker:{WORKER_ID}"
    while True:
        try:
            payload = {
                "worker_id": WORKER_ID,
                "active_jobs": len(active_tasks),
                "concurrency": CONCURRENCY,
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "started_at": started_at_iso,
                "status": "online",
            }
            await redis_client.set(key, json.dumps(payload), ex=10)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Failed to send heartbeat: {e}")
        await asyncio.sleep(3)


async def main_loop():
    """Worker main polling loop with signal-aware graceful shutdown."""
    logger.info(f"Initializing Forge Worker [{WORKER_ID}] with CONCURRENCY={CONCURRENCY}")

    redis_client = aioredis.from_url(REDIS_URI, decode_responses=True)
    try:
        await redis_client.ping()
        logger.info(f"Connected to Redis at {REDIS_URI}")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return

    semaphore = asyncio.Semaphore(CONCURRENCY)
    active_tasks: Set[asyncio.Task] = set()
    started_at_iso = datetime.now(timezone.utc).isoformat()
    shutdown_requested = False

    # Start background heartbeat task
    hb_task = asyncio.create_task(heartbeat_loop(redis_client, active_tasks, started_at_iso))

    def handle_signal(sig, frame):
        nonlocal shutdown_requested
        sig_name = signal.Signals(sig).name
        logger.info(f"Received {sig_name}. Initiating graceful shutdown...")
        shutdown_requested = True

    loop = asyncio.get_running_loop()
    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: handle_signal(s, None))
    except NotImplementedError:
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

    logger.info("Worker polling loop active. Waiting for jobs...")

    while not shutdown_requested:
        try:
            # Promote matured delayed jobs into ready queue
            await promote_delayed_jobs(redis_client)

            # Check for available queue job atomically (lowest score = highest priority)
            pop_result = await redis_client.zpopmin(QUEUE_KEY, count=1)

            if pop_result:
                job_id_str, score = pop_result[0]
                logger.info(f"Dequeued job_id={job_id_str} (score={score})")

                task = asyncio.create_task(
                    process_job(job_id_str, redis_client, semaphore)
                )
                active_tasks.add(task)
                task.add_done_callback(active_tasks.discard)
            else:
                await asyncio.sleep(POLL_INTERVAL)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in worker poll loop: {e}")
            await asyncio.sleep(POLL_INTERVAL)

    logger.info(f"Stop receiving jobs. Waiting for {len(active_tasks)} active tasks to finish...")

    if active_tasks:
        done, pending = await asyncio.wait(active_tasks, timeout=30.0)
        if pending:
            logger.warning(f"Shutdown timeout reached with {len(pending)} tasks still pending. Cancelling...")
            for p_task in pending:
                p_task.cancel()

    logger.info("Closing database engine and Redis pool...")
    hb_task.cancel()
    try:
        await redis_client.delete(f"forge:worker:{WORKER_ID}")
    except Exception:
        pass
    await redis_client.aclose()
    await engine.dispose()
    logger.info("Worker shutdown complete.")


def main():
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received. Exiting.")


if __name__ == "__main__":
    main()
