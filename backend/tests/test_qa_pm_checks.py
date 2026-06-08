"""Tests for QAAgent check_pm_sections advisory checks (M13B)."""

import pytest

from app.agents.qa_agent import check_pm_sections
from app.schemas.pm_sections import (
    FeatureInsights,
    GtmProfile,
    MarketBackground,
    OperationMonetization,
)
from app.schemas.qa import IssueSeverity, IssueType
from app.schemas.report import CompetitiveReport


def _make_report(**kwargs) -> CompetitiveReport:
    return CompetitiveReport(project_id="proj_test", **kwargs)


def test_check_pm_sections_all_absent_returns_three_medium_issues():
    report = _make_report()
    issues = check_pm_sections(report)
    assert len(issues) == 3
    assert all(i.severity == IssueSeverity.medium for i in issues)
    types = {i.issue_type for i in issues}
    assert IssueType.missing_market_background in types
    assert IssueType.missing_feature_insights in types
    assert IssueType.missing_operation_monetization in types


def test_check_pm_sections_all_populated_returns_no_issues():
    report = _make_report(
        market_background=MarketBackground(market_overview="Competitive AI market."),
        feature_insights=FeatureInsights(table_stakes=["Code completion"]),
        operation_monetization=OperationMonetization(
            gtm_profiles=[GtmProfile(competitor_name="Cursor", motion="PLG")]
        ),
    )
    assert check_pm_sections(report) == []


def test_check_pm_sections_only_market_background_missing():
    report = _make_report(
        feature_insights=FeatureInsights(table_stakes=["AI chat"]),
        operation_monetization=OperationMonetization(
            gtm_profiles=[GtmProfile(competitor_name="Trae", motion="PLG")]
        ),
    )
    issues = check_pm_sections(report)
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.missing_market_background


def test_check_pm_sections_empty_overview_triggers_issue():
    report = _make_report(
        market_background=MarketBackground(market_overview=""),  # empty string = absent
        feature_insights=FeatureInsights(table_stakes=["Code completion"]),
        operation_monetization=OperationMonetization(
            gtm_profiles=[GtmProfile(competitor_name="Windsurf", motion="PLG")]
        ),
    )
    issues = check_pm_sections(report)
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.missing_market_background


def test_check_pm_sections_called_in_run():
    """Integration smoke: check_pm_sections issues appear in QAAgent run output (mocked DB)."""
    from unittest.mock import MagicMock, patch

    from app.agents import qa_agent

    report = _make_report()  # no PM sections → 3 advisory issues
    mock_db = MagicMock()

    with patch("app.services.trace_service.save_agent_run"), \
         patch("app.services.qa_service.save_qa_result"):
        result = qa_agent.run(
            db=mock_db,
            project_id="proj_smoke",
            report=report,
            knowledge=[],
            sources=[],
            goals=["feature_comparison"],
        )

    pm_types = {
        IssueType.missing_market_background,
        IssueType.missing_feature_insights,
        IssueType.missing_operation_monetization,
    }
    found_types = {i.issue_type for i in result.issues}
    assert pm_types.issubset(found_types)
    # All three are medium severity — do not flip pass/fail on their own
    pm_issues = [i for i in result.issues if i.issue_type in pm_types]
    assert all(i.severity == IssueSeverity.medium for i in pm_issues)
