"""
Integration Test: Job Lifecycle End-to-End.

Tests the full lifecycle of a job through the Forge system:
  1. Submit a job via POST /jobs
  2. Verify it appears as 'queued'
  3. Retrieve it via GET /jobs/{id}
  4. Delete it and verify 404

Prerequisites:
  - Postgres and Redis must be running (use docker compose up -d).

Usage:
    cd api
    pytest ../tests/integration/test_job_lifecycle.py -v -s
"""

import uuid
import pytest
import httpx

import sys
import os

# Add the api directory to the Python path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "api"))

from app.main import app


API_KEY = "forge_dev_key_123"
HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture
async def client():
    """Create an httpx async client bound to the FastAPI ASGI app."""
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver/api",
        ) as c:
            yield c


class TestJobLifecycle:
    """End-to-end lifecycle tests for job submission and processing."""

    @pytest.mark.asyncio
    async def test_submit_job_returns_queued(self, client):
        """POST /jobs should return 201 with status 'queued'."""
        key = f"integration_{uuid.uuid4().hex[:12]}"
        response = await client.post(
            "/jobs",
            json={
                "job_type": "send_email",
                "payload": {"to": "integration@test.com"},
                "idempotency_key": key,
            },
            headers=HEADERS,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "queued"
        assert body["job_type"] == "send_email"
        assert body["attempts"] == 0

        # Cleanup
        await client.delete(f"/jobs/{body['id']}", headers=HEADERS)

    @pytest.mark.asyncio
    async def test_get_job_after_creation(self, client):
        """GET /jobs/{id} should return the job we just created."""
        key = f"integration_{uuid.uuid4().hex[:12]}"
        create_resp = await client.post(
            "/jobs",
            json={
                "job_type": "generate_report",
                "payload": {"report_type": "test"},
                "idempotency_key": key,
            },
            headers=HEADERS,
        )
        job_id = create_resp.json()["id"]

        get_resp = await client.get(f"/jobs/{job_id}", headers=HEADERS)
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == job_id
        assert get_resp.json()["status"] == "queued"

        # Cleanup
        await client.delete(f"/jobs/{job_id}", headers=HEADERS)

    @pytest.mark.asyncio
    async def test_list_jobs_with_status_filter(self, client):
        """GET /jobs?status=queued should return only queued jobs."""
        key = f"integration_{uuid.uuid4().hex[:12]}"
        create_resp = await client.post(
            "/jobs",
            json={
                "job_type": "send_email",
                "payload": {},
                "idempotency_key": key,
            },
            headers=HEADERS,
        )
        job_id = create_resp.json()["id"]

        list_resp = await client.get("/jobs?status=queued", headers=HEADERS)
        assert list_resp.status_code == 200
        body = list_resp.json()
        assert body["total"] >= 1
        statuses = [j["status"] for j in body["jobs"]]
        assert all(s == "queued" for s in statuses)

        # Cleanup
        await client.delete(f"/jobs/{job_id}", headers=HEADERS)

    @pytest.mark.asyncio
    async def test_delete_job(self, client):
        """DELETE /jobs/{id} should remove the job and return 204."""
        key = f"integration_{uuid.uuid4().hex[:12]}"
        create_resp = await client.post(
            "/jobs",
            json={
                "job_type": "resize_image",
                "payload": {},
                "idempotency_key": key,
            },
            headers=HEADERS,
        )
        job_id = create_resp.json()["id"]

        # Delete
        del_resp = await client.delete(f"/jobs/{job_id}", headers=HEADERS)
        assert del_resp.status_code == 204

        # Verify it's gone
        get_resp = await client.get(f"/jobs/{job_id}", headers=HEADERS)
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_pagination(self, client):
        """GET /jobs should respect page and per_page parameters."""
        # Create 3 jobs
        created_ids = []
        for i in range(3):
            key = f"integration_page_{uuid.uuid4().hex[:8]}"
            resp = await client.post(
                "/jobs",
                json={
                    "job_type": "send_email",
                    "payload": {"index": i},
                    "idempotency_key": key,
                },
                headers=HEADERS,
            )
            created_ids.append(resp.json()["id"])

        # Request page 1 with per_page=2
        list_resp = await client.get(
            "/jobs?page=1&per_page=2", headers=HEADERS
        )
        body = list_resp.json()
        assert len(body["jobs"]) <= 2
        assert body["page"] == 1
        assert body["per_page"] == 2

        # Cleanup
        for jid in created_ids:
            await client.delete(f"/jobs/{jid}", headers=HEADERS)

    @pytest.mark.asyncio
    async def test_health_endpoint(self, client):
        """GET /health should return overall system health."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as root_client:
            resp = await root_client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] in ("healthy", "degraded")
        assert "database" in body
        assert "redis" in body
