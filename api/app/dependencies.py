"""
FastAPI Dependencies for Authentication & Rate Limiting.
"""

from typing import Optional
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.database import get_db
from app.redis import get_redis
from app.models_db import APIKey
from app.services.rate_limiter import check_rate_limit


async def verify_api_key_and_rate_limit(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> APIKey:
    """
    FastAPI dependency that:
    1. Validates the presence and authenticity of the X-API-Key header.
    2. Enforces per-API-key sliding-window rate limiting.
    3. Returns the APIKey ORM object on success.
    4. Raises HTTP 401 if missing/invalid, or HTTP 429 + Retry-After header if limit exceeded.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required header: X-API-Key",
        )

    # 1. Query database for API Key
    result = await db.execute(
        select(APIKey).where(APIKey.key == x_api_key, APIKey.is_active == True)
    )
    api_key_obj = result.scalars().first()

    if not api_key_obj:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or deactivated API key",
        )

    # 2. Check sliding-window rate limit in Redis
    is_allowed, retry_after, current_count = await check_rate_limit(
        redis=redis,
        api_key=api_key_obj.key,
        limit_rpm=api_key_obj.rate_limit_rpm,
    )

    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded ({api_key_obj.rate_limit_rpm} requests/min limit).",
            headers={"Retry-After": str(retry_after)},
        )

    return api_key_obj
