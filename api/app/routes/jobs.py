"""
Job CRUD endpoints.

POST /jobs      — Idempotent job creation → Postgres + Redis queue
GET  /jobs/{id} — Retrieve a single job (cached: memory → Redis → Postgres)
GET  /jobs      — List jobs with optional status filter + pagination
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.database import get_db
from app.redis import get_redis
from app.models_db import Job, APIKey
from app.dependencies import verify_api_key_and_rate_limit
from app.services.queue import enqueue_job, remove_job_from_queue
from app.services.cache import get_cached_job, set_cached_job, invalidate_job_cache
from app.services.events import publish_job_event
from forge_shared import JobCreate, JobListResponse, JobResponse, JobStatus

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _job_to_dict(job: Job) -> dict:
    """Convert a SQLAlchemy Job row to a plain dict suitable for caching."""
    return {
        "id": str(job.id),
        "idempotency_key": job.idempotency_key,
        "job_type": job.job_type,
        "payload": job.payload,
        "status": job.status,
        "priority": job.priority,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "run_after": job.run_after.isoformat() if job.run_after else None,
        "result": job.result,
        "error": job.error,
    }


# --------------------------------------------------------------------------- #
# POST /jobs — Idempotent job creation
# --------------------------------------------------------------------------- #
@router.post(
    "",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new job",
    description=(
        "Insert a job into the queue. If a job with the same idempotency_key "
        "already exists, the existing job is returned (HTTP 200) instead of "
        "creating a duplicate."
    ),
)
async def create_job(
    body: JobCreate,
    response: Response = None,  # injected by FastAPI
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    api_key: APIKey = Depends(verify_api_key_and_rate_limit),
):
    """
    Race-condition strategy
    ────────────────────────
    We use PostgreSQL's  INSERT ... ON CONFLICT (idempotency_key) DO NOTHING.

    Two concurrent requests with the same key will serialise on the unique-index
    row lock.  The "winner" inserts; the "loser" gets DO NOTHING (zero rows
    returned by RETURNING).  We then SELECT the existing row for the loser.

    Why not SELECT-then-INSERT?
      → A TOCTOU race: between the SELECT and the INSERT another transaction
        can sneak in.  ON CONFLICT is a single atomic statement — no gap.

    Why not INSERT ... ON CONFLICT DO UPDATE (upsert)?
      → We don't want the second caller to silently mutate the first job's
        payload.  DO NOTHING preserves the original job untouched.

    Enqueue-after-commit strategy
    ─────────────────────────────
    We push to Redis AFTER the Postgres commit succeeds. This means:
      • If Postgres fails → no Redis entry (correct: job doesn't exist).
      • If Redis fails → job is in Postgres but not in the queue.
        A recovery sweeper (Phase 3+) can detect "queued" jobs in Postgres
        that aren't in Redis and re-enqueue them.
    This ordering preference is called "write-ahead to durable store" —
    it's better to have a job that exists but isn't queued (recoverable)
    than a queued job that doesn't exist in Postgres (data loss).
    """

    # Build the INSERT ... ON CONFLICT DO NOTHING ... RETURNING * statement.
    stmt = (
        pg_insert(Job)
        .values(
            job_type=body.job_type,
            payload=body.payload,
            idempotency_key=body.idempotency_key,
            priority=body.priority,
            run_after=body.run_after,
            max_attempts=body.max_attempts,
            status="queued",
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(Job)
    )

    result = await db.execute(stmt)
    row = result.scalars().first()

    if row is not None:
        # New job was inserted — commit and enqueue to Redis.
        await db.commit()
        await db.refresh(row)

        # Push to Redis priority queue (after Postgres commit).
        await enqueue_job(
            redis,
            job_id=str(row.id),
            priority=body.priority,
            run_after=body.run_after,
        )

        # Publish live event to Redis Pub/Sub
        await publish_job_event(redis, job_id=str(row.id), old_status=None, new_status="queued")

        return row

    # Conflict path: the idempotency_key already exists.
    # The winning transaction is guaranteed committed by the time we reach here
    # (the unique-index lock blocked us until the winner committed).
    await db.rollback()  # clean up the empty transaction

    existing = await db.execute(
        select(Job).where(Job.idempotency_key == body.idempotency_key)
    )
    existing_job = existing.scalars().first()

    if existing_job is None:
        # Shouldn't happen — defensive guard.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Idempotency conflict detected but existing job not found",
        )

    # Signal to the client that this was a duplicate, not a new creation.
    # Override the default 201 to 200 via FastAPI's injected Response object.
    response.status_code = status.HTTP_200_OK
    return existing_job


# --------------------------------------------------------------------------- #
# GET /jobs/{job_id} — Single job lookup (with cache)
# --------------------------------------------------------------------------- #
@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get a job by ID",
    description=(
        "Retrieve a single job. Results are served from a two-tier cache "
        "(in-memory 2s TTL → Redis 10s TTL) to avoid hammering Postgres "
        "on repeated dashboard polls."
    ),
)
async def get_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    job_id_str = str(job_id)

    # --- Cache read-through ---
    cached = await get_cached_job(redis, job_id_str)
    if cached is not None:
        return cached

    # --- Cache miss: query Postgres ---
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalars().first()

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    # Backfill both cache tiers
    job_dict = _job_to_dict(job)
    await set_cached_job(redis, job_id_str, job_dict)

    return job


# --------------------------------------------------------------------------- #
# GET /jobs — Paginated list with optional status filter
# --------------------------------------------------------------------------- #
@router.get(
    "",
    response_model=JobListResponse,
    summary="List jobs",
)
async def list_jobs(
    status_filter: JobStatus | None = Query(
        default=None,
        alias="status",
        description="Filter by job status",
    ),
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(
        default=20, ge=1, le=100, description="Items per page (max 100)"
    ),
    db: AsyncSession = Depends(get_db),
):
    # Base query
    query = select(Job)
    count_query = select(func.count(Job.id))

    # Apply optional status filter
    if status_filter is not None:
        query = query.where(Job.status == status_filter.value)
        count_query = count_query.where(Job.status == status_filter.value)

    # Get total count
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Apply ordering and pagination
    offset = (page - 1) * per_page
    query = query.order_by(Job.created_at.desc()).offset(offset).limit(per_page)

    result = await db.execute(query)
    jobs = result.scalars().all()

    return JobListResponse(
        jobs=jobs,
        total=total,
        page=page,
        per_page=per_page,
    )


# --------------------------------------------------------------------------- #
# DELETE /jobs/{job_id} — Delete a single job
# --------------------------------------------------------------------------- #
@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a job by ID",
)
async def delete_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    job_id_str = str(job_id)

    # Fetch to ensure it exists
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalars().first()

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    # Delete from DB
    await db.delete(job)
    await db.commit()

    # Remove from Redis queues and cache
    await remove_job_from_queue(redis, job_id_str)
    await invalidate_job_cache(redis, job_id_str)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
