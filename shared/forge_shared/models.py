from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from uuid import UUID


class JobStatus(str, Enum):
    """
    Job lifecycle states. See docs/job-lifecycle.md for the full state machine.

    queued    → Job accepted, waiting to be picked up by a worker.
    running   → A worker has claimed the job and is executing it.
    succeeded → Job completed successfully; result stored.
    failed    → Job's current attempt failed; may transition to retrying or dead.
    retrying  → Job failed but has remaining attempts; will be re-queued.
    dead      → Job exhausted all retry attempts; terminal failure state.
    """
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD = "dead"
    CANCELLED = "cancelled"


class JobCreate(BaseModel):
    """Schema for the POST /jobs request body."""
    job_type: str = Field(
        ...,
        description="Task type identifier (e.g. 'send_email', 'generate_report')",
        min_length=1,
        max_length=255,
    )
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary JSON input parameters for the job handler",
    )
    idempotency_key: str = Field(
        ...,
        description="Client-supplied unique key to prevent duplicate job creation",
        min_length=1,
        max_length=255,
    )
    priority: int = Field(
        default=0,
        ge=0,
        description="Priority level; higher values are dequeued first",
    )
    run_after: Optional[datetime] = Field(
        default=None,
        description="Earliest time the job should be executed (for delayed jobs)",
    )
    max_attempts: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Maximum number of execution attempts before moving to dead state",
    )


class JobResponse(BaseModel):
    """Schema for job data returned by the API."""
    id: UUID
    idempotency_key: str
    job_type: str
    payload: Dict[str, Any]
    status: JobStatus
    priority: int
    attempts: int
    max_attempts: int
    created_at: datetime
    updated_at: datetime
    run_after: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    class Config:
        from_attributes = True


class JobListResponse(BaseModel):
    """Paginated list wrapper for GET /jobs."""
    jobs: List[JobResponse]
    total: int
    page: int
    per_page: int
