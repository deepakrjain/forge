"""
Sliding Window Rate Limiter using Redis Sorted Sets and Lua scripts.

Tradeoff Rationale: Sliding Window Log vs. Fixed Window (INCR + EXPIRE)
════════════════════════════════════════════════════════════════════════

Fixed Window (INCR + EXPIRE):
  - Increments a counter for a fixed key like `ratelimit:key:2026-08-03-12:00`.
  - Pro: Extremely fast (single `INCR` operation).
  - Con: Boundary burst vulnerability. If a key has a limit of 60 req/min, a client
    can send 60 requests at 11:59:59 and 60 requests at 12:00:00. This passes the rate
    limiter but allows 120 requests in a 2-second window (2x capacity burst).

Sliding Window Log (Our Choice):
  - Stores request timestamps as elements in a Redis Sorted Set (`forge:ratelimit:{api_key}`).
  - Evaluates the exact rolling 60-second window relative to the current timestamp.
  - Automatically prunes timestamps older than `now - window_ms` using `ZREMRANGEBYSCORE`.
  - Pro: Guarantees strict rate limit compliance across any arbitrary rolling window.
  - Con: Uses slightly more memory in Redis to store request timestamps, cleaned up
    automatically via `ZREMRANGEBYSCORE` and `PEXPIRE`.
"""

import time
import uuid
import math
import logging
from typing import Tuple

import redis.asyncio as aioredis

logger = logging.getLogger("forge.ratelimit")

# Redis Lua Script for atomic sliding window rate checking
SLIDING_WINDOW_LUA_SCRIPT = """
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local max_limit = tonumber(ARGV[3])
local request_id = ARGV[4]

-- 1. Remove request logs older than the rolling window start
local window_start = now_ms - window_ms
redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)

-- 2. Count active requests in current window
local current_requests = redis.call('ZCARD', key)

if current_requests >= max_limit then
    -- Rate limit exceeded. Fetch oldest request timestamp to calculate exact Retry-After
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local oldest_ts = tonumber(oldest[2]) or window_start
    local reset_ms = (oldest_ts + window_ms) - now_ms
    local retry_after_sec = math.ceil(reset_ms / 1000)
    if retry_after_sec < 1 then retry_after_sec = 1 end
    return {0, retry_after_sec, current_requests}
end

-- 3. Allowed: record request timestamp and set TTL on sorted set
redis.call('ZADD', key, now_ms, request_id)
redis.call('PEXPIRE', key, window_ms)
return {1, 0, current_requests + 1}
"""


async def check_rate_limit(
    redis: aioredis.Redis,
    api_key: str,
    limit_rpm: int,
    window_seconds: int = 60,
) -> Tuple[bool, int, int]:
    """
    Check rate limit for a given API key using a sliding window log.

    Returns:
        (is_allowed: bool, retry_after_seconds: int, current_count: int)
    """
    now_ms = int(time.time() * 1000)
    window_ms = window_seconds * 1000
    request_id = f"{now_ms}-{uuid.uuid4().hex[:8]}"
    redis_key = f"forge:ratelimit:{api_key}"

    try:
        res = await redis.eval(
            SLIDING_WINDOW_LUA_SCRIPT,
            1,
            redis_key,
            now_ms,
            window_ms,
            limit_rpm,
            request_id,
        )
        is_allowed = bool(res[0])
        retry_after = int(res[1])
        count = int(res[2])

        if not is_allowed:
            logger.warning(
                f"Rate limit EXCEEDED for key '{api_key}' ({count}/{limit_rpm} rpm). "
                f"Retry-After: {retry_after}s"
            )
        return is_allowed, retry_after, count
    except Exception as e:
        logger.error(f"Error evaluating rate limit script for key '{api_key}': {e}")
        # Fail open in case of Redis errors to prevent total API blackout
        return True, 0, 0
