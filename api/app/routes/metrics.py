"""
Metrics endpoint providing real-time system stats:
- Job status counts
- Queue depth by priority
- Active worker / running count
- DLQ count and success rate
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.database import get_db
from app.redis import get_redis
from app.models_db import Job
from forge_shared import JobStatus

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get(
    "",
    summary="Get system metrics",
    description="Returns job counts by status, priority breakdown, success rate, and active worker stats.",
)
async def get_metrics(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    # Counts by status
    status_counts_res = await db.execute(
        select(Job.status, func.count(Job.id)).group_by(Job.status)
    )
    status_counts = {row[0]: row[1] for row in status_counts_res.all()}

    # Ensure all statuses have a count
    for s in JobStatus:
        if s.value not in status_counts:
            status_counts[s.value] = 0

    # Queue depth by priority tier
    high_res = await db.execute(
        select(func.count(Job.id)).where(Job.status == "queued", Job.priority >= 7)
    )
    normal_res = await db.execute(
        select(func.count(Job.id)).where(
            Job.status == "queued", Job.priority >= 4, Job.priority < 7
        )
    )
    low_res = await db.execute(
        select(func.count(Job.id)).where(Job.status == "queued", Job.priority < 4)
    )

    priority_breakdown = {
        "high": high_res.scalar_one(),
        "normal": normal_res.scalar_one(),
        "low": low_res.scalar_one(),
    }

    total_jobs = sum(status_counts.values())
    succeeded = status_counts.get("succeeded", 0)
    failed = status_counts.get("failed", 0)
    dead = status_counts.get("dead", 0)

    completed = succeeded + failed + dead
    success_rate = (succeeded / completed * 100.0) if completed > 0 else 100.0

    return {
        "status_counts": status_counts,
        "priority_breakdown": priority_breakdown,
        "total_jobs": total_jobs,
        "active_running": status_counts.get("running", 0),
        "dlq_count": dead,
        "success_rate": round(success_rate, 1),
    }
