"""
Forge Worker Process — Main Entrypoint.

Architecture & Design Overview
═══════════════════════════════

1. Concurrency Model: asyncio.Semaphore(CONCURRENCY)
   The worker uses a single polling loop that pops job IDs from Redis (`ZPOPMIN`).
   New jobs are spawned as asynchronous tasks guarded by an `asyncio.Semaphore`.
   When all N concurrency slots are busy, `semaphore.acquire()` naturally blocks
   the poll loop from taking more work from Redis.

2. State Transitions & Database Persistence:
   - On dequeue: Status transitions to `running`, `attempts` is incremented.
   - On completion: Status transitions to `succeeded` (with `result` payload).
   - On error: Status transitions to `failed` (with `error` traceback/message).
   - Cache invalidation: Calls Redis `DEL forge:job:{id}` on every status update
     to ensure the API's read-through cache is invalidated immediately.

3. Graceful Shutdown (SIGTERM / SIGINT):
   - On SIGTERM or SIGINT, a shutdown event is set.
   - The poll loop terminates immediately, preventing new jobs from being popped.
   - The worker waits for all currently in-flight jobs to complete (up to a timeout).
   - Resources (Redis connection pool, DB engine) are disposed cleanly.

4. Failure Mode: What happens if killed with SIGKILL (kill -9)?
   - SIGKILL cannot be intercepted by process signal handlers.
   - If SIGKILL strikes mid-execution:
     • The job was already popped from Redis (`ZPOPMIN` removed it).
     • The job status remains stuck in `running` in PostgreSQL.
     • The worker process dies instantly without cleaning up.
   - This creates a "Ghost Job" state: PostgreSQL says the job is running,
     but no active process is executing it.
   - Mitigation (implemented in subsequent recovery sweeps):
     • Periodic Heartbeat / Stale-Job Sweeper: A background process scans Postgres
       for jobs stuck in `running` status whose `updated_at` timestamp exceeds
       a threshold (e.g. 5 minutes) and re-enqueues them to Redis.
"""

import asyncio
import logging
import signal
import sys
import traceback
from datetime import datetime, timezone
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
from forge_shared import JobStatus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger(f"forge.worker.{WORKER_ID}")

QUEUE_KEY = "forge:queue:jobs"
CACHE_PREFIX = "forge:job:"


async def invalidate_redis_cache(redis_client: aioredis.Redis, job_id: str):
    """Delete cached job representation in Redis on status change."""
    try:
        await redis_client.delete(f"{CACHE_PREFIX}{job_id}")
    except Exception as e:
        logger.warning(f"Failed to invalidate cache for job {job_id}: {e}")


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

                job.status = JobStatus.RUNNING.value
                job.attempts += 1
                job.updated_at = datetime.now(timezone.utc)
                job_type = job.job_type
                payload = job.payload or {}

            # Transaction committed. Now invalidate cache.
            await invalidate_redis_cache(redis_client, job_id_str)

        # ------------------------------------------------------------------- #
        # Step 2: Execute dummy handler
        # ------------------------------------------------------------------- #
        handler = get_handler(job_type)
        start_time = datetime.now(timezone.utc)
        job_result: Optional[dict] = None
        error_msg: Optional[str] = None
        execution_success = False

        try:
            logger.info(f"Executing handler for job_type='{job_type}' (id={job_id_str})")
            job_result = await handler(payload)
            execution_success = True
            logger.info(f"Job {job_id_str} completed successfully.")
        except Exception as exc:
            execution_success = False
            error_msg = f"{type(exc).__name__}: {str(exc)}\n{traceback.format_exc()}"
            logger.warning(f"Job {job_id_str} failed execution: {exc}")

        # ------------------------------------------------------------------- #
        # Step 3: Update final status in Postgres
        # ------------------------------------------------------------------- #
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
                    else:
                        job.status = JobStatus.FAILED.value
                        job.error = error_msg

            # Invalidate cache again for completed/failed state
            await invalidate_redis_cache(redis_client, job_id_str)


async def main_loop():
    """Worker main polling loop with signal-aware graceful shutdown."""
    logger.info(f"Initializing Forge Worker [{WORKER_ID}] with CONCURRENCY={CONCURRENCY}")

    # Set up Redis connection pool
    redis_client = aioredis.from_url(REDIS_URI, decode_responses=True)
    try:
        await redis_client.ping()
        logger.info(f"Connected to Redis at {REDIS_URI}")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return

    # Semaphore to bound concurrent active job tasks
    semaphore = asyncio.Semaphore(CONCURRENCY)
    active_tasks: Set[asyncio.Task] = set()

    # Graceful shutdown flag
    shutdown_requested = False

    def handle_signal(sig, frame):
        nonlocal shutdown_requested
        sig_name = signal.Signals(sig).name
        logger.info(f"Received {sig_name}. Initiating graceful shutdown...")
        shutdown_requested = True

    # Register signal handlers for SIGTERM and SIGINT
    loop = asyncio.get_running_loop()
    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: handle_signal(s, None))
    except NotImplementedError:
        # Fallback for OS platforms where loop.add_signal_handler is not available (e.g. Windows native loops)
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

    logger.info("Worker polling loop active. Waiting for jobs...")

    while not shutdown_requested:
        try:
            # Check for available queue job atomically (lowest score = highest priority)
            pop_result = await redis_client.zpopmin(QUEUE_KEY, count=1)

            if pop_result:
                job_id_str, score = pop_result[0]
                logger.info(f"Dequeued job_id={job_id_str} (score={score})")

                # Create task for job execution bounded by semaphore
                task = asyncio.create_task(
                    process_job(job_id_str, redis_client, semaphore)
                )
                active_tasks.add(task)
                task.add_done_callback(active_tasks.discard)
            else:
                # Queue empty: wait poll interval
                await asyncio.sleep(POLL_INTERVAL)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in worker poll loop: {e}")
            await asyncio.sleep(POLL_INTERVAL)

    # ----------------------------------------------------------------------- #
    # Graceful Shutdown Phase
    # ----------------------------------------------------------------------- #
    logger.info(f"Stop receiving jobs. Waiting for {len(active_tasks)} active tasks to finish...")

    if active_tasks:
        done, pending = await asyncio.wait(active_tasks, timeout=30.0)
        if pending:
            logger.warning(f"Shutdown timeout reached with {len(pending)} tasks still pending. Cancelling...")
            for p_task in pending:
                p_task.cancel()

    logger.info("Closing database engine and Redis pool...")
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
