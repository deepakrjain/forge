"""
Dead Letter Queue (DLQ) endpoints.

GET  /dlq           — List dead jobs (status = 'dead') with pagination
POST /dlq/{id}/retry — Manually re-enqueue a dead job, resetting attempts to 0
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.database import get_db
from app.redis import get_redis
from app.models_db import Job
from app.services.queue import enqueue_job, remove_from_dlq
from app.services.cache import invalidate_job_cache
from forge_shared import JobListResponse, JobResponse, JobStatus

router = APIRouter(prefix="/dlq", tags=["dlq"])


# --------------------------------------------------------------------------- #
# GET /dlq — Paginated list of dead jobs
# --------------------------------------------------------------------------- #
@router.get(
    "",
    response_model=JobListResponse,
    summary="List dead jobs in DLQ",
    description="Retrieve all jobs that have exhausted max_attempts and entered the dead state.",
)
async def list_dlq_jobs(
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
):
    query = select(Job).where(Job.status == JobStatus.DEAD.value)
    count_query = select(func.count(Job.id)).where(Job.status == JobStatus.DEAD.value)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * per_page
    query = query.order_by(Job.updated_at.desc()).offset(offset).limit(per_page)

    result = await db.execute(query)
    jobs = result.scalars().all()

    return JobListResponse(
        jobs=jobs,
        total=total,
        page=page,
        per_page=per_page,
    )


# --------------------------------------------------------------------------- #
# POST /dlq/{job_id}/retry — Manually retry a dead job
# --------------------------------------------------------------------------- #
@router.post(
    "/{job_id}/retry",
    response_model=JobResponse,
    summary="Retry a dead job from DLQ",
    description=(
        "Reset a dead job's attempt count to 0, clear error history, set status back to queued, "
        "and re-enqueue it into the Redis ready queue."
    ),
)
async def retry_dead_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    job_id_str = str(job_id)

    async with db.begin():
        result = await db.execute(
            select(Job).where(Job.id == job_id).with_for_update()
        )
        job = result.scalars().first()

        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found",
            )

        if job.status != JobStatus.DEAD.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Job {job_id} is in status '{job.status}', not 'dead'. Only dead jobs can be retried via DLQ.",
            )

        # Reset job state
        job.status = JobStatus.QUEUED.value
        job.attempts = 0
        job.error = None
        job.result = None
        job.run_after = None

    # Database committed. Now update Redis & cache.
    await remove_from_dlq(redis, job_id_str)
    await enqueue_job(redis, job_id_str, priority=job.priority)
    await invalidate_job_cache(redis, job_id_str)

    return job
