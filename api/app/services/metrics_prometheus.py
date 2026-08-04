"""
Prometheus Metrics Registry and Exporter for Forge.

Exposes standard Prometheus instruments:
  - jobs_enqueued_total (Counter, label: job_type)
  - jobs_succeeded_total (Counter, label: job_type)
  - jobs_failed_total (Counter, label: job_type)
  - jobs_dead_total (Counter, label: job_type)
  - queue_depth (Gauge, label: priority_tier)
  - active_workers (Gauge)
"""

import json
import logging
from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.models_db import Job
from forge_shared import JobStatus

logger = logging.getLogger("forge.metrics.prometheus")

# Create dedicated registry to avoid duplicate metrics across reloads
REGISTRY = CollectorRegistry()

# ── Counters ────────────────────────────────────────────────────────────────
JOBS_ENQUEUED_TOTAL = Counter(
    "jobs_enqueued_total",
    "Total number of jobs enqueued into Forge queue",
    ["job_type"],
    registry=REGISTRY,
)

JOBS_SUCCEEDED_TOTAL = Counter(
    "jobs_succeeded_total",
    "Total number of jobs successfully executed",
    ["job_type"],
    registry=REGISTRY,
)

JOBS_FAILED_TOTAL = Counter(
    "jobs_failed_total",
    "Total number of job execution attempts that failed",
    ["job_type"],
    registry=REGISTRY,
)

JOBS_DEAD_TOTAL = Counter(
    "jobs_dead_total",
    "Total number of jobs moved to Dead Letter Queue (max attempts exhausted)",
    ["job_type"],
    registry=REGISTRY,
)

# ── Gauges ──────────────────────────────────────────────────────────────────
QUEUE_DEPTH = Gauge(
    "queue_depth",
    "Current number of jobs waiting in ready queue by priority tier",
    ["priority_tier"],
    registry=REGISTRY,
)

ACTIVE_WORKERS = Gauge(
    "active_workers",
    "Number of active worker nodes with unexpired heartbeats in Redis",
    registry=REGISTRY,
)


async def sync_prometheus_metrics(db: AsyncSession, redis: aioredis.Redis):
    """
    Query database and Redis to update Prometheus gauges and counter baselines on scrape.
    Ensures metrics remain consistent across API restarts and horizontal instances.
    """
    try:
        # 1. Job totals by type & status from DB
        status_type_res = await db.execute(
            select(Job.job_type, Job.status, func.count(Job.id)).group_by(
                Job.job_type, Job.status
            )
        )
        rows = status_type_res.all()

        # Reset & update counters from DB state
        for job_type, status_val, count in rows:
            if status_val == JobStatus.SUCCEEDED.value:
                JOBS_SUCCEEDED_TOTAL.labels(job_type=job_type)._value.set(float(count))
            elif status_val == JobStatus.FAILED.value:
                JOBS_FAILED_TOTAL.labels(job_type=job_type)._value.set(float(count))
            elif status_val == JobStatus.DEAD.value:
                JOBS_DEAD_TOTAL.labels(job_type=job_type)._value.set(float(count))

        # Enqueued total (all jobs ever created)
        enqueued_res = await db.execute(
            select(Job.job_type, func.count(Job.id)).group_by(Job.job_type)
        )
        for job_type, count in enqueued_res.all():
            JOBS_ENQUEUED_TOTAL.labels(job_type=job_type)._value.set(float(count))

        # 2. Queue Depth Gauges by Priority Tier
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

        QUEUE_DEPTH.labels(priority_tier="high").set(float(high_res.scalar_one()))
        QUEUE_DEPTH.labels(priority_tier="normal").set(float(normal_res.scalar_one()))
        QUEUE_DEPTH.labels(priority_tier="low").set(float(low_res.scalar_one()))

        # 3. Active Workers Gauge from Redis heartbeats
        keys = await redis.keys("forge:worker:*")
        ACTIVE_WORKERS.set(len(keys))

    except Exception as e:
        logger.warning(f"Error syncing Prometheus metrics: {e}")


def get_prometheus_payload() -> bytes:
    """Generate Prometheus exposition text format bytes."""
    return generate_latest(REGISTRY)
