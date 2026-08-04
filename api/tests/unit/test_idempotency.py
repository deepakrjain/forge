"""
Unit Tests for Idempotency Key Logic.

Tests the POST /jobs endpoint's idempotent creation behaviour:
  - First request with a unique key → 201 Created
  - Duplicate request with the same key → 200 OK (returns existing job)
  - Two different keys → two separate jobs

These tests use httpx.AsyncClient with the real FastAPI app against
the live Postgres and Redis instances (same dev database). We clean up
our test data after each test using a unique idempotency key prefix.
"""

import uuid
import pytest
import httpx
from contextlib import asynccontextmanager

from app.main import app


API_KEY_HEADER = {"X-API-Key": "forge_dev_key_123"}


def _unique_key() -> str:
    """Generate a unique idempotency key for testing."""
    return f"test_idem_{uuid.uuid4().hex[:12]}"


@pytest.fixture
async def client():
    """Create an httpx async client bound to the FastAPI app with lifespan."""
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver/api",
        ) as c:
            yield c


@pytest.fixture
async def cleanup_jobs(client):
    """Track and delete jobs created during tests."""
    created_ids: list[str] = []
    yield created_ids
    # Clean up: delete each job we created
    for job_id in created_ids:
        try:
            await client.delete(f"/jobs/{job_id}", headers=API_KEY_HEADER)
        except Exception:
            pass


class TestIdempotencyKey:
    """Test suite for the idempotency key mechanism on POST /jobs."""

    @pytest.mark.asyncio
    async def test_first_submission_returns_201(self, client, cleanup_jobs):
        """A brand-new idempotency key should create a job and return 201."""
        key = _unique_key()
        response = await client.post(
            "/jobs",
            json={
                "job_type": "send_email",
                "payload": {"to": "test@example.com"},
                "idempotency_key": key,
                "priority": 0,
            },
            headers=API_KEY_HEADER,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["idempotency_key"] == key
        assert body["status"] == "queued"
        assert body["job_type"] == "send_email"
        cleanup_jobs.append(body["id"])

    @pytest.mark.asyncio
    async def test_duplicate_key_returns_200(self, client, cleanup_jobs):
        """Sending the same idempotency key twice should return 200 (not 201)."""
        key = _unique_key()

        # First submission
        r1 = await client.post(
            "/jobs",
            json={
                "job_type": "send_email",
                "payload": {"to": "first@example.com"},
                "idempotency_key": key,
            },
            headers=API_KEY_HEADER,
        )
        assert r1.status_code == 201
        first_id = r1.json()["id"]
        cleanup_jobs.append(first_id)

        # Duplicate submission with the same key
        r2 = await client.post(
            "/jobs",
            json={
                "job_type": "send_email",
                "payload": {"to": "second@example.com"},
                "idempotency_key": key,
            },
            headers=API_KEY_HEADER,
        )
        assert r2.status_code == 200  # Not 201 — existing job returned

    @pytest.mark.asyncio
    async def test_duplicate_returns_same_job_id(self, client, cleanup_jobs):
        """The duplicate response should contain the exact same job ID."""
        key = _unique_key()

        r1 = await client.post(
            "/jobs",
            json={
                "job_type": "resize_image",
                "payload": {"width": 800},
                "idempotency_key": key,
            },
            headers=API_KEY_HEADER,
        )
        first_id = r1.json()["id"]
        cleanup_jobs.append(first_id)

        r2 = await client.post(
            "/jobs",
            json={
                "job_type": "resize_image",
                "payload": {"width": 1200},
                "idempotency_key": key,
            },
            headers=API_KEY_HEADER,
        )
        second_id = r2.json()["id"]

        assert first_id == second_id

    @pytest.mark.asyncio
    async def test_duplicate_preserves_original_payload(self, client, cleanup_jobs):
        """The duplicate should NOT overwrite the first job's payload."""
        key = _unique_key()
        original_payload = {"subject": "original"}

        r1 = await client.post(
            "/jobs",
            json={
                "job_type": "send_email",
                "payload": original_payload,
                "idempotency_key": key,
            },
            headers=API_KEY_HEADER,
        )
        cleanup_jobs.append(r1.json()["id"])

        r2 = await client.post(
            "/jobs",
            json={
                "job_type": "send_email",
                "payload": {"subject": "overwritten"},
                "idempotency_key": key,
            },
            headers=API_KEY_HEADER,
        )

        # The returned payload should still be the original
        assert r2.json()["payload"] == original_payload

    @pytest.mark.asyncio
    async def test_different_keys_create_different_jobs(self, client, cleanup_jobs):
        """Two requests with different idempotency keys should create two separate jobs."""
        key1 = _unique_key()
        key2 = _unique_key()

        r1 = await client.post(
            "/jobs",
            json={
                "job_type": "generate_report",
                "payload": {},
                "idempotency_key": key1,
            },
            headers=API_KEY_HEADER,
        )
        assert r1.status_code == 201
        cleanup_jobs.append(r1.json()["id"])

        r2 = await client.post(
            "/jobs",
            json={
                "job_type": "generate_report",
                "payload": {},
                "idempotency_key": key2,
            },
            headers=API_KEY_HEADER,
        )
        assert r2.status_code == 201
        cleanup_jobs.append(r2.json()["id"])

        assert r1.json()["id"] != r2.json()["id"]
