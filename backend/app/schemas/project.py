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
    "unknown",
    "build_product",
    "choose_product",
    "understand_industry",
    "analyze_growth_ops",
]
AnalysisFramework = Literal["swot", "three_c", "aarrr"]

LEGACY_ANALYSIS_PURPOSES: dict[str, AnalysisPurpose] = {
    "build_similar_product": "build_product",
    "choose_product_to_use": "choose_product",
    "market_research": "understand_industry",
    "competitor_success_analysis": "analyze_growth_ops",
    "industry_landscape": "understand_industry",
    "competitor_success": "analyze_growth_ops",
    "improve_product": "build_product",
    "general": "unknown",
}
DEFAULT_ANALYSIS_PURPOSE: AnalysisPurpose = "unknown"
DEFAULT_ANALYSIS_FRAMEWORKS: list[AnalysisFramework] = ["swot"]


def normalize_analysis_purpose(value: str | None, *, strict: bool = False) -> AnalysisPurpose:
    raw = (value or DEFAULT_ANALYSIS_PURPOSE).strip()
    if raw in LEGACY_ANALYSIS_PURPOSES:
        return LEGACY_ANALYSIS_PURPOSES[raw]
    if raw in get_args(AnalysisPurpose):
        return raw
    if strict:
        raise ValueError(f"Unsupported analysis_purpose: {raw}")
    return DEFAULT_ANALYSIS_PURPOSE


def normalize_analysis_frameworks(values: list[str] | None) -> list[AnalysisFramework]:
    allowed = set(get_args(AnalysisFramework))
    result: list[AnalysisFramework] = []
    for value in values or DEFAULT_ANALYSIS_FRAMEWORKS:
        raw = str(value).strip()
        if raw == "3c":
            raw = "three_c"
        if raw in allowed and raw not in result:
            result.append(raw)  # type: ignore[arg-type]
    return result or list(DEFAULT_ANALYSIS_FRAMEWORKS)


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
    analysis_frameworks: list[AnalysisFramework] = Field(default_factory=lambda: list(DEFAULT_ANALYSIS_FRAMEWORKS))
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

    @field_validator("analysis_frameworks", mode="before")
    @classmethod
    def normalize_frameworks(cls, value: list[str] | None) -> list[AnalysisFramework]:
        return normalize_analysis_frameworks(value)


class ProjectResponse(BaseModel):
    project_id: str
    industry: str
    industry_type: str = "general"
    analysis_purpose: str = DEFAULT_ANALYSIS_PURPOSE
    analysis_frameworks: list[str] = []
    custom_dimensions: list[str] = []
    goals: list[str]
    status: ProjectStatus
    output_language: str
    created_at: str
    updated_at: str
    data_mode: str = "demo"
    research_inputs: list[ResearchInput] = []
    competitors: list[CompetitorInProject] = []
