"""Competitive analysis report schema.

The final report aggregates structured knowledge for each competitor and
adds comparison tables, executive summary claims, and a source list.
"""

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.schemas.claim import Claim
from app.schemas.knowledge import CompetitorKnowledge
from app.schemas.pm_sections import FeatureInsights, MarketBackground, OperationMonetization
from app.schemas.scoring import CompetitorScore, OpportunityScore
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
    analysis_purpose: str = "general"
    analysis_objective: str = ""
    competitor_selection_rationale: dict = Field(default_factory=dict)
    purpose_sections: dict = Field(default_factory=dict)
    competitor_scores: dict[str, CompetitorScore] = Field(default_factory=dict)
    opportunity_score: OpportunityScore | None = None
    custom_dimension_analysis: dict = Field(default_factory=dict)
    # M13B: PM-framework sections (always generated)
    market_background: MarketBackground | None = None
    feature_insights: FeatureInsights | None = None
    operation_monetization: OperationMonetization | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
