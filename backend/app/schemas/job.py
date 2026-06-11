"""Workflow job schemas."""

from enum import Enum

from pydantic import BaseModel, Field


class WorkflowJobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class WorkflowJobResponse(BaseModel):
    job_id: str
    project_id: str
    status: WorkflowJobStatus
    backend: str
    attempts: int = 0
    created_at: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    error_message: str | None = None


class WorkflowRunAccepted(BaseModel):
    project_id: str
    status: str
    job_id: str = Field(description="Persistent workflow job id")
