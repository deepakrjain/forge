"""
Prometheus metrics exposition endpoint.

GET /metrics — Returns system metrics in Prometheus text exposition format (version 0.0.4).
"""

from fastapi import APIRouter, Depends, Response
from prometheus_client import CONTENT_TYPE_LATEST
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.database import get_db
from app.redis import get_redis
from app.services.metrics_prometheus import (
    sync_prometheus_metrics,
    get_prometheus_payload,
)

router = APIRouter(tags=["metrics"])


@router.get(
    "/metrics",
    summary="Prometheus Metrics",
    description="Exposes system telemetry (counters & gauges) in standard Prometheus text format.",
)
async def metrics_endpoint(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    await sync_prometheus_metrics(db, redis)
    payload = get_prometheus_payload()
    return Response(content=payload, media_type=CONTENT_TYPE_LATEST)
