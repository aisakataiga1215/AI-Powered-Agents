"""Project schema.

Defines request and response models for project creation and status
retrieval. These map to the REST endpoints documented in
``engineering_spec.md`` section 11.
"""

from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.competitor import CompetitorInput


class ProjectStatus(str, Enum):
    created = "created"
    running = "running"
    completed = "completed"
    qa_failed = "qa_failed"
    failed = "failed"


class ProjectCreate(BaseModel):
    industry: str
    competitors: list[CompetitorInput]
    goals: list[str] = Field(default_factory=list)
    output_language: str = "zh"
    report_depth: str = "standard"


class ProjectResponse(BaseModel):
    project_id: str
    industry: str
    goals: list[str]
    status: ProjectStatus
    created_at: str
    updated_at: str
