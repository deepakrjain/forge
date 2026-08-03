from enum import Enum
from typing import Any, Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobBase(BaseModel):
    name: str = Field(..., description="Name or task type of the job")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Input parameters for the job")
    priority: int = Field(default=0, description="Priority level (higher numbers executed first)")


class JobCreate(JobBase):
    pass


class JobResponse(JobBase):
    id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    class Config:
        from_attributes = True
