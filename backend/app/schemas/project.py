"""Project schema.

Defines request and response models for project creation and status
retrieval. These map to the REST endpoints documented in
``engineering_spec.md`` section 11.
"""

from enum import Enum
from typing import Literal, get_args

from pydantic import BaseModel, Field, field_validator

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
    "build_similar_product",
    "choose_product_to_use",
    "market_research",
    "competitor_success_analysis",
]

LEGACY_ANALYSIS_PURPOSES: dict[str, AnalysisPurpose] = {
    "build_product": "build_similar_product",
    "choose_product": "choose_product_to_use",
    "industry_landscape": "market_research",
    "competitor_success": "competitor_success_analysis",
    "improve_product": "build_similar_product",
    "general": "market_research",
}
DEFAULT_ANALYSIS_PURPOSE: AnalysisPurpose = "market_research"


def normalize_analysis_purpose(value: str | None, *, strict: bool = False) -> AnalysisPurpose:
    raw = (value or DEFAULT_ANALYSIS_PURPOSE).strip()
    if raw in LEGACY_ANALYSIS_PURPOSES:
        return LEGACY_ANALYSIS_PURPOSES[raw]
    if raw in get_args(AnalysisPurpose):
        return raw
    if strict:
        raise ValueError(f"Unsupported analysis_purpose: {raw}")
    return DEFAULT_ANALYSIS_PURPOSE


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
    analysis_purpose: AnalysisPurpose = DEFAULT_ANALYSIS_PURPOSE
    custom_dimensions: list[str] = Field(default_factory=list)
    competitors: list[CompetitorInput]
    goals: list[str] = Field(default_factory=list)
    output_language: str = "en"
    report_depth: str = "standard"
    data_mode: Literal["demo", "live_with_fallback"] = "demo"
    research_inputs: list[ResearchInput] = Field(default_factory=list)

    @field_validator("analysis_purpose", mode="before")
    @classmethod
    def normalize_purpose(cls, value: str | None) -> AnalysisPurpose:
        return normalize_analysis_purpose(value, strict=True)


class ProjectResponse(BaseModel):
    project_id: str
    industry: str
    industry_type: str = "general"
    analysis_purpose: str = DEFAULT_ANALYSIS_PURPOSE
    custom_dimensions: list[str] = []
    goals: list[str]
    status: ProjectStatus
    output_language: str
    created_at: str
    updated_at: str
    data_mode: str = "demo"
    research_inputs: list[ResearchInput] = []
    competitors: list[CompetitorInProject] = []
