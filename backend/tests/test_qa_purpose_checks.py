"""Tests for QAAgent advisory purpose-aware checks."""

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.agents.qa_agent import check_custom_dimensions, check_scoring_rationale
from app.schemas.report import CompetitiveReport
from app.schemas.qa import IssueSeverity


def _make_report(**kwargs) -> CompetitiveReport:
    defaults = {
        "project_id": "proj_test",
        "title": "Test Report",
        "executive_summary": [],
        "competitor_overview": [],
        "feature_comparison": {},
        "pricing_comparison": {},
        "user_persona_comparison": {},
        "swot_comparison": {},
        "strategic_recommendations": [],
        "source_list": [],
        "markdown_content": "",
    }
    defaults.update(kwargs)
    return CompetitiveReport(**defaults)


# ---------------------------------------------------------------------------
# check_custom_dimensions
# ---------------------------------------------------------------------------


def test_check_custom_dimensions_empty_list_returns_no_issues():
    report = _make_report()
    assert check_custom_dimensions(report, []) == []


def test_check_custom_dimensions_dim_not_in_content_returns_medium_issue():
    report = _make_report(markdown_content="some unrelated content")
    issues = check_custom_dimensions(report, ["API quality"])
    assert len(issues) == 1
    assert issues[0].severity is IssueSeverity.medium
    assert "API quality" in issues[0].message


def test_check_custom_dimensions_dim_found_in_analysis_keys_returns_no_issue():
    report = _make_report(
        custom_dimension_analysis={"API quality": {"CompA": {"score": 4, "rationale": "good"}}},
    )
    issues = check_custom_dimensions(report, ["API quality"])
    assert issues == []


def test_check_custom_dimensions_dim_found_in_markdown_returns_no_issue():
    report = _make_report(markdown_content="The api quality is excellent.")
    issues = check_custom_dimensions(report, ["api quality"])
    assert issues == []


# ---------------------------------------------------------------------------
# check_scoring_rationale
# ---------------------------------------------------------------------------


def test_check_scoring_rationale_market_research_returns_no_issues():
    report = _make_report()
    assert check_scoring_rationale(report, "market_research") == []


def test_check_scoring_rationale_choose_product_missing_scores_returns_medium():
    report = _make_report(competitor_scores={})
    issues = check_scoring_rationale(report, "choose_product_to_use")
    assert len(issues) == 1
    assert issues[0].severity is IssueSeverity.medium
    assert "competitor_scores" in issues[0].message


def test_check_scoring_rationale_build_product_missing_opportunity_score_returns_medium():
    report = _make_report(opportunity_score=None)
    issues = check_scoring_rationale(report, "build_similar_product")
    assert len(issues) == 1
    assert issues[0].severity is IssueSeverity.medium
    assert "opportunity_score" in issues[0].message
