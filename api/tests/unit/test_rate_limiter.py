"""
Unit Tests for the Sliding Window Rate Limiter.

Tests the check_rate_limit function from app.services.rate_limiter,
verifying that the Lua-based sliding window correctly allows/denies
requests and returns accurate retry-after values.

These tests use a real Redis instance (localhost:6379) to execute the
Lua scripts atomically — mocking Redis.eval wouldn't meaningfully test
the rate limiting logic since it lives in the Lua script itself.
"""

import asyncio
import time
import pytest
import redis.asyncio as aioredis

from app.services.rate_limiter import check_rate_limit


@pytest.fixture
async def redis_client():
    """Create a fresh Redis connection for each test."""
    client = aioredis.from_url("redis://localhost:6379/0", decode_responses=True)
    try:
        await client.ping()
    except Exception:
        pytest.skip("Redis not available on localhost:6379")
    yield client
    await client.aclose()


@pytest.fixture(autouse=True)
async def cleanup_rate_limit_keys(redis_client):
    """Clean up any rate limit keys after each test."""
    yield
    # Delete test keys
    keys = await redis_client.keys("forge:ratelimit:test_*")
    if keys:
        await redis_client.delete(*keys)


class TestCheckRateLimit:
    """Test suite for the sliding window rate limiter."""

    @pytest.mark.asyncio
    async def test_first_request_is_allowed(self, redis_client):
        """The very first request should always be allowed."""
        is_allowed, retry_after, count = await check_rate_limit(
            redis=redis_client,
            api_key="test_first_request",
            limit_rpm=10,
        )
        assert is_allowed is True
        assert retry_after == 0
        assert count == 1

    @pytest.mark.asyncio
    async def test_requests_within_limit_are_allowed(self, redis_client):
        """All requests under the limit should be allowed."""
        key = "test_within_limit"
        limit = 5

        for i in range(limit):
            is_allowed, retry_after, count = await check_rate_limit(
                redis=redis_client,
                api_key=key,
                limit_rpm=limit,
            )
            assert is_allowed is True, f"Request {i+1}/{limit} should be allowed"
            assert count == i + 1

    @pytest.mark.asyncio
    async def test_request_exceeding_limit_is_denied(self, redis_client):
        """The request that crosses the limit should be denied."""
        key = "test_exceed_limit"
        limit = 3

        # Use up all allowed requests
        for _ in range(limit):
            await check_rate_limit(
                redis=redis_client,
                api_key=key,
                limit_rpm=limit,
            )

        # This one should be denied
        is_allowed, retry_after, count = await check_rate_limit(
            redis=redis_client,
            api_key=key,
            limit_rpm=limit,
        )
        assert is_allowed is False
        assert retry_after > 0
        assert count >= limit

    @pytest.mark.asyncio
    async def test_retry_after_is_positive_integer(self, redis_client):
        """When rate-limited, retry_after should be a positive integer (seconds)."""
        key = "test_retry_after"
        limit = 1

        await check_rate_limit(redis=redis_client, api_key=key, limit_rpm=limit)
        is_allowed, retry_after, _ = await check_rate_limit(
            redis=redis_client, api_key=key, limit_rpm=limit
        )

        assert is_allowed is False
        assert isinstance(retry_after, int)
        assert retry_after >= 1

    @pytest.mark.asyncio
    async def test_different_keys_have_independent_limits(self, redis_client):
        """Rate limits for different API keys should not interfere."""
        limit = 2

        # Exhaust limit for key A
        for _ in range(limit):
            await check_rate_limit(
                redis=redis_client, api_key="test_key_a", limit_rpm=limit
            )

        # Key A should be denied
        is_allowed_a, _, _ = await check_rate_limit(
            redis=redis_client, api_key="test_key_a", limit_rpm=limit
        )
        assert is_allowed_a is False

        # Key B should still be allowed
        is_allowed_b, _, _ = await check_rate_limit(
            redis=redis_client, api_key="test_key_b", limit_rpm=limit
        )
        assert is_allowed_b is True

    @pytest.mark.asyncio
    async def test_window_expiry_allows_new_requests(self, redis_client):
        """After the sliding window expires, requests should be allowed again."""
        key = "test_window_expiry"
        limit = 1
        window = 1  # 1-second window for fast test

        # First request should be allowed
        is_allowed, _, _ = await check_rate_limit(
            redis=redis_client, api_key=key, limit_rpm=limit, window_seconds=window
        )
        assert is_allowed is True

        # Second should be denied
        is_allowed, _, _ = await check_rate_limit(
            redis=redis_client, api_key=key, limit_rpm=limit, window_seconds=window
        )
        assert is_allowed is False

        # Wait for the window to expire
        await asyncio.sleep(1.1)

        # Now it should be allowed again
        is_allowed, _, _ = await check_rate_limit(
            redis=redis_client, api_key=key, limit_rpm=limit, window_seconds=window
        )
        assert is_allowed is True

    @pytest.mark.asyncio
    async def test_count_tracks_active_requests(self, redis_client):
        """The count return value should reflect how many requests are in the window."""
        key = "test_count_tracking"
        limit = 10

        for expected_count in range(1, 6):
            _, _, count = await check_rate_limit(
                redis=redis_client, api_key=key, limit_rpm=limit
            )
            assert count == expected_count
