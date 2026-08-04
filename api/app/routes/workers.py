"""
Worker status endpoints.

GET /workers — List active worker nodes and their heartbeat metrics.
"""

import json
from fastapi import APIRouter, Depends
import redis.asyncio as aioredis

from app.redis import get_redis

router = APIRouter(prefix="/workers", tags=["workers"])


@router.get(
    "",
    summary="List active workers",
    description="Retrieve live heartbeats of active worker processes from Redis.",
)
async def list_workers(redis: aioredis.Redis = Depends(get_redis)):
    keys = await redis.keys("forge:worker:*")
    workers = []

    for key in keys:
        raw_val = await redis.get(key)
        if raw_val:
            try:
                data = json.loads(raw_val)
                workers.append(data)
            except Exception:
                pass

    # Sort workers by worker_id
    workers.sort(key=lambda w: w.get("worker_id", ""))

    return {
        "workers": workers,
        "total": len(workers),
    }
