"""Competitive analysis report schema.

The final report aggregates structured knowledge for each competitor and
adds comparison tables, executive summary claims, and a source list.
"""

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.schemas.claim import Claim
from app.schemas.knowledge import CompetitorKnowledge
from app.schemas.source import SourceEvidence


class CompetitiveReport(BaseModel):
    report_id: str = Field(default_factory=lambda: f"rpt_{uuid.uuid4().hex[:8]}")
    # ``project_id`` is bound by the WriterAgent after generation. Leaving
    # it as a required field caused some OpenAI-compatible providers to
    # silently fail structured-output validation when the LLM omitted it.
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
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
