import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum as PgEnum,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase

from forge_shared import JobStatus


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


class Job(Base):
    """
    SQLAlchemy model for the `jobs` table.

    Key index choices:
    - UNIQUE on idempotency_key: enforces exactly-once creation at the DB level.
    - INDEX on status: nearly every worker query filters by status.
    - INDEX on priority DESC: workers dequeue highest-priority jobs first.
    - INDEX on job_type: supports dashboard filtering by task type.
    """

    __tablename__ = "jobs"

    # --- Primary key ---
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    # --- Idempotency ---
    idempotency_key = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    # --- Job definition ---
    job_type = Column(String(255), nullable=False, index=True)
    payload = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    # --- State machine ---
    status = Column(
        PgEnum(
            "queued", "running", "succeeded", "failed", "retrying", "dead",
            name="job_status_enum",
            create_type=True,
        ),
        nullable=False,
        default="queued",
        server_default="queued",
        index=True,
    )

    # --- Execution control ---
    priority = Column(Integer, nullable=False, default=0, server_default=text("0"))
    attempts = Column(Integer, nullable=False, default=0, server_default=text("0"))
    max_attempts = Column(Integer, nullable=False, default=3, server_default=text("3"))
    run_after = Column(DateTime(timezone=True), nullable=True)

    # --- Output ---
    result = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)

    # --- Timestamps ---
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<Job id={self.id} type={self.job_type} status={self.status}>"
