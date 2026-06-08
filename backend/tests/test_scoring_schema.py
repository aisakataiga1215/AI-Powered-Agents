"""Tests for scoring schemas: DimensionScore, CompetitorScore, OpportunityScore."""

import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from pydantic import ValidationError

from app.schemas.scoring import CompetitorScore, DimensionScore, OpportunityDimension, OpportunityScore


def test_dimension_score_rejects_score_below_1():
    with pytest.raises(ValidationError):
        DimensionScore(dimension_name="ease_of_use", score=0, rationale="too low")


def test_dimension_score_rejects_score_above_5():
    with pytest.raises(ValidationError):
        DimensionScore(dimension_name="ease_of_use", score=6, rationale="too high")


def test_competitor_score_rejects_overall_score_above_100():
    with pytest.raises(ValidationError):
        CompetitorScore(competitor_name="Cursor", overall_score=101)


def test_opportunity_score_validates_with_two_dimensions():
    score = OpportunityScore(
        overall_score=72.5,
        dimensions=[
            OpportunityDimension(dimension_name="market_gap", score=4, rationale="large gap"),
            OpportunityDimension(dimension_name="feasibility", score=3, rationale="moderate"),
        ],
    )
    assert score.overall_score == 72.5
    assert len(score.dimensions) == 2
    assert score.dimensions[0].dimension_name == "market_gap"


def test_dimension_score_defaults_source_confidence_to_medium():
    d = DimensionScore(dimension_name="pricing_value", score=3, rationale="ok")
    assert d.source_confidence == "medium"


def test_competitor_score_has_default_scoring_note():
    cs = CompetitorScore(competitor_name="Trae", overall_score=80.0)
    assert "model-assisted" in cs.scoring_note
