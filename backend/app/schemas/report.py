"""Competitive analysis report schema.

The final report aggregates structured knowledge for each competitor and
adds comparison tables, executive summary claims, and a source list.
"""

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.schemas.claim import Claim
from app.schemas.knowledge import CompetitorKnowledge
from app.schemas.scoring import CompetitorScore
from app.schemas.source import SourceEvidence


class CompetitiveReport(BaseModel):
    report_id: str = Field(default_factory=lambda: f"rpt_{uuid.uuid4().hex[:8]}")
    project_id: str = ""
    title: str = "Competitive Analysis Report"
    executive_summary: list[Claim] = Field(default_factory=list)
    competitor_overview: list[CompetitorKnowledge] = Field(default_factory=list)
    feature_comparison: dict = Field(default_factory=dict)
    pricing_comparison: dict = Field(default_factory=dict)
    user_persona_comparison: dict = Field(default_factory=dict)
    swot_comparison: dict = Field(default_factory=dict)
    strategic_recommendations: list[Claim] = Field(default_factory=list)
    source_list: list[SourceEvidence] = Field(default_factory=list)
    markdown_content: str = ""
    # M13A: purpose-aware analysis fields
    analysis_purpose: str = "unknown"
    analysis_frameworks: list[str] = Field(default_factory=lambda: ["swot"])
    selected_report_tabs: list[str] = Field(default_factory=list)
    framework_sections: dict = Field(default_factory=dict)
    custom_dimension_sections: dict = Field(default_factory=dict)
    purpose_sections: dict = Field(default_factory=dict)
    competitor_scores: dict[str, CompetitorScore] = Field(default_factory=dict)
    analysis_objective: str = ""
    competitor_selection_rationale: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
