"""Project schema.

Defines request and response models for project creation and status
retrieval. These map to the REST endpoints documented in
``engineering_spec.md`` section 11.
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.competitor import CompetitorInput, CompetitorRole

IndustryType = Literal[
    "ai_saas",
    "ai_search",
    "design_tools",
    "ecommerce",
    "local_services",
    "open_source",
    "social",
    "general",
]
AnalysisPurpose = Literal[
    "build_product",
    "choose_product",
    "industry_landscape",
    "competitor_success",
    "improve_product",
    "general",
]


class ProjectStatus(str, Enum):
    created = "created"
    running = "running"
    completed = "completed"
    qa_failed = "qa_failed"
    failed = "failed"


class CompetitorInProject(BaseModel):
    name: str
    url: str
    role: CompetitorRole = "direct_competitor"
    extra_urls: list[str] = Field(default_factory=list)


class ResearchInput(BaseModel):
    title: str = Field(default="User research notes", max_length=160)
    content: str = Field(min_length=1, max_length=12000)
    source_kind: Literal["survey", "interview", "questionnaire", "desk_research", "notes"] = "notes"
    competitor_name: str = ""


class ProjectCreate(BaseModel):
    industry: str
    industry_type: IndustryType = "general"
    analysis_purpose: AnalysisPurpose = "general"
    custom_dimensions: list[str] = Field(default_factory=list)
    competitors: list[CompetitorInput]
    goals: list[str] = Field(default_factory=list)
    output_language: str = "en"
    report_depth: str = "standard"
    data_mode: Literal["demo", "live_with_fallback"] = "demo"
    research_inputs: list[ResearchInput] = Field(default_factory=list)


class ProjectResponse(BaseModel):
    project_id: str
    industry: str
    industry_type: str = "general"
    analysis_purpose: str = "general"
    custom_dimensions: list[str] = []
    goals: list[str]
    status: ProjectStatus
    output_language: str
    created_at: str
    updated_at: str
    data_mode: str = "demo"
    research_inputs: list[ResearchInput] = []
    competitors: list[CompetitorInProject] = []
