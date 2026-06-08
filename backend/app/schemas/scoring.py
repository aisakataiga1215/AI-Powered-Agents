"""Scoring schemas for purpose-aware analysis.

CompetitorScore is used for choose_product analysis (one score per competitor).
OpportunityScore is used for build_product analysis (single market opportunity score).
"""

from typing import Literal

from pydantic import BaseModel, Field

SourceConfidence = Literal["high", "medium", "low", "unknown"]


class DimensionScore(BaseModel):
    dimension_name: str
    score: int = Field(ge=1, le=5)
    rationale: str
    evidence: list[str] = Field(default_factory=list)
    source_confidence: SourceConfidence = "medium"


class CompetitorScore(BaseModel):
    competitor_name: str
    overall_score: float = Field(ge=0, le=100)
    dimensions: list[DimensionScore] = Field(default_factory=list)
    scoring_note: str = "Scores are model-assisted evaluations, not objective measurements."


class OpportunityDimension(BaseModel):
    dimension_name: str
    score: int = Field(ge=1, le=5)
    rationale: str
    evidence: list[str] = Field(default_factory=list)
    source_confidence: SourceConfidence = "medium"


class OpportunityScore(BaseModel):
    overall_score: float = Field(ge=0, le=100)
    dimensions: list[OpportunityDimension] = Field(default_factory=list)
    scoring_note: str = "Scores are model-assisted evaluations, not objective measurements."
