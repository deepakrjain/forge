import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
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


class APIKey(Base):
    """
    SQLAlchemy model for API authentication keys and rate limits.
    """

    __tablename__ = "api_keys"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    key = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    rate_limit_rpm = Column(Integer, nullable=False, default=60, server_default=text("60"))
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )

    def __repr__(self) -> str:
        return f"<APIKey key={self.key} name={self.name} rpm={self.rate_limit_rpm}>"


class Job(Base):
    """
    SQLAlchemy model for the `jobs` table.
    """

    __tablename__ = "jobs"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    idempotency_key = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    job_type = Column(String(255), nullable=False, index=True)
    payload = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

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

    priority = Column(Integer, nullable=False, default=0, server_default=text("0"))
    attempts = Column(Integer, nullable=False, default=0, server_default=text("0"))
    max_attempts = Column(Integer, nullable=False, default=3, server_default=text("3"))
    run_after = Column(DateTime(timezone=True), nullable=True)

    result = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)

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
