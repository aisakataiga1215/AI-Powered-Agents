"""Scoring schemas for purpose-aware product selection."""

from typing import Literal

from pydantic import BaseModel, Field

SourceConfidence = Literal["high", "medium", "low", "unknown"]


class DimensionScore(BaseModel):
    dimension_name: str
    score: int = Field(ge=1, le=5)
    weight: float = Field(ge=0, le=1)
    rationale: str
    evidence: list[str] = Field(default_factory=list)
    source_confidence: SourceConfidence = "medium"


class CompetitorScore(BaseModel):
    competitor_name: str
    overall_score: float = Field(ge=0, le=100)
    dimensions: list[DimensionScore] = Field(default_factory=list)
    scoring_note: str = (
        "Scores are weighted decision-support estimates based on collected "
        "evidence, not objective measurements."
    )
