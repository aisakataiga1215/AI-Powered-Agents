"""Tests for QAAgent per-competitor source coverage checks."""

import pytest

from app.schemas.qa import IssueSeverity, IssueType, QAResult, QAIssue
from app.schemas.source import SourceEvidence, SourceType
from app.schemas.knowledge import CompetitorKnowledge, ProductProfile
from app.agents.qa_agent import check_source_coverage, check_source_quality, check_brand_consistency


def _make_source(competitor_name: str, source_type: SourceType) -> SourceEvidence:
    return SourceEvidence(
        competitor_name=competitor_name,
        source_type=source_type,
        url=f"https://example.com/{source_type.value}",
        title=f"{competitor_name} {source_type.value}",
    )


class TestCheckSourceCoverage:
    def test_no_issues_when_goals_not_set(self):
        sources = [_make_source("Cursor", SourceType.official_website)]
        issues: list = []
        check_source_coverage(sources, goals=[], issues=issues)
        assert issues == []

    def test_pricing_issue_for_competitor_missing_pricing_source(self):
        sources = [
            _make_source("Trae", SourceType.official_website),
        ]
        issues: list = []
        check_source_coverage(sources, goals=["pricing_analysis"], issues=issues)
        assert len(issues) == 1
        assert issues[0].issue_type == IssueType.missing_pricing_source
        assert issues[0].severity == IssueSeverity.high
        assert "Trae" in issues[0].message

    def test_no_pricing_issue_when_competitor_has_pricing_source(self):
        sources = [
            _make_source("Cursor", SourceType.official_website),
            _make_source("Cursor", SourceType.pricing_page),
        ]
        issues: list = []
        check_source_coverage(sources, goals=["pricing_analysis"], issues=issues)
        assert issues == []

    def test_pricing_issue_only_for_competitor_without_pricing(self):
        sources = [
            _make_source("Cursor", SourceType.official_website),
            _make_source("Cursor", SourceType.pricing_page),
            _make_source("Trae", SourceType.official_website),
        ]
        issues: list = []
        check_source_coverage(sources, goals=["pricing_analysis"], issues=issues)
        assert len(issues) == 1
        assert "Trae" in issues[0].message
        assert "Cursor" not in issues[0].message

    def test_features_issue_for_competitor_missing_features_source(self):
        sources = [_make_source("Windsurf", SourceType.official_website)]
        issues: list = []
        check_source_coverage(sources, goals=["feature_comparison"], issues=issues)
        assert len(issues) == 1
        assert issues[0].issue_type == IssueType.missing_features_source
        assert issues[0].severity == IssueSeverity.medium
        assert "Windsurf" in issues[0].message

    def test_no_features_issue_when_competitor_has_docs_source(self):
        sources = [
            _make_source("Cursor", SourceType.official_website),
            _make_source("Cursor", SourceType.docs),
        ]
        issues: list = []
        check_source_coverage(sources, goals=["feature_comparison"], issues=issues)
        assert issues == []

    def test_no_features_issue_when_competitor_has_features_page(self):
        sources = [
            _make_source("Cursor", SourceType.features_page),
        ]
        issues: list = []
        check_source_coverage(sources, goals=["feature_comparison"], issues=issues)
        assert issues == []

    def test_multiple_competitors_independent_issues(self):
        sources = [
            _make_source("Cursor", SourceType.pricing_page),
            _make_source("Trae", SourceType.official_website),
            _make_source("Windsurf", SourceType.official_website),
        ]
        issues: list = []
        check_source_coverage(sources, goals=["pricing_analysis"], issues=issues)
        affected = {i.message for i in issues}
        assert any("Trae" in m for m in affected)
        assert any("Windsurf" in m for m in affected)
        assert not any("Cursor" in m for m in affected)

    def test_all_coverage_present_no_issues(self):
        sources = [
            _make_source("Cursor", SourceType.official_website),
            _make_source("Cursor", SourceType.pricing_page),
            _make_source("Cursor", SourceType.docs),
        ]
        issues: list = []
        check_source_coverage(
            sources,
            goals=["pricing_analysis", "feature_comparison"],
            issues=issues,
        )
        assert issues == []

    def test_target_agent_is_collector(self):
        sources = [_make_source("Trae", SourceType.official_website)]
        issues: list = []
        check_source_coverage(sources, goals=["pricing_analysis"], issues=issues)
        assert all(i.target_agent == "CollectorAgent" for i in issues)


class TestCheckSourceQuality:
    """Tests for check_source_quality() — TDD: will fail before implementation."""

    def test_pricing_source_with_discord_content_triggers_high_issue(self):
        source = SourceEvidence(
            competitor_name="Windsurf",
            source_type=SourceType.pricing_page,
            url="https://windsurf.com/pricing",
            title="Discord",
            content="Join the Windsurf community on Discord. You need to create an account.",
        )
        issues: list = []
        check_source_quality([source], issues)
        assert len(issues) == 1
        assert issues[0].severity == IssueSeverity.high
        assert issues[0].issue_type == IssueType.weak_source_quality

    def test_pricing_source_with_weak_content_triggers_medium_issue(self):
        source = SourceEvidence(
            competitor_name="Acme",
            source_type=SourceType.pricing_page,
            url="https://acme.com/pricing",
            title="About Acme",
            content="We are a software company focused on developer tools in San Francisco.",
        )
        issues: list = []
        check_source_quality([source], issues)
        assert len(issues) == 1
        assert issues[0].severity == IssueSeverity.medium

    def test_valid_pricing_source_not_flagged(self):
        source = SourceEvidence(
            competitor_name="Cursor",
            source_type=SourceType.pricing_page,
            url="https://cursor.com/pricing",
            title="Pricing Plans",
            content="Hobby plan: free. Pro plan: $20/month per user. Enterprise subscription.",
        )
        issues: list = []
        check_source_quality([source], issues)
        assert len(issues) == 0

    def test_unknown_type_source_not_checked(self):
        source = SourceEvidence(
            competitor_name="Windsurf",
            source_type=SourceType.unknown,
            url="https://windsurf.com/pricing",
            title="Discord",
            content="Join the Discord community.",
        )
        issues: list = []
        check_source_quality([source], issues)
        assert len(issues) == 0


class TestQAScoreInvariant:
    def _issue(self, severity: IssueSeverity) -> QAIssue:
        return QAIssue(
            severity=severity,
            issue_type=IssueType.weak_source_quality,
            target_agent="CollectorAgent",
            message="test issue",
        )

    def test_empty_issues_always_yields_score_100(self):
        result = QAResult(project_id="p", passed=True, score=95, issues=[])
        assert result.score == 100

    def test_one_high_issue_deducts_15(self):
        result = QAResult(project_id="p", passed=False, issues=[self._issue(IssueSeverity.high)])
        assert result.score == 85

    def test_one_medium_issue_deducts_5(self):
        result = QAResult(project_id="p", passed=False, issues=[self._issue(IssueSeverity.medium)])
        assert result.score == 95

    def test_low_issue_deducts_nothing(self):
        result = QAResult(project_id="p", passed=True, issues=[self._issue(IssueSeverity.low)])
        assert result.score == 100


def _minimal_knowledge(name: str, website: str = "") -> CompetitorKnowledge:
    return CompetitorKnowledge(
        competitor_id=f"comp_{name.lower()}",
        competitor_name=name,
        product_profile=ProductProfile(name=name, website=website),
    )


class TestCheckBrandConsistency:
    def test_prominent_known_brand_triggers_low_issue(self):
        # Devin is not a project competitor but is in _PRODUCT_BRAND_MAP for Windsurf
        knowledge = [_minimal_knowledge("Windsurf", "https://windsurf.com")]
        source = SourceEvidence(
            competitor_name="Windsurf",
            source_type=SourceType.official_website,
            url="https://windsurf.com/about",
            title="About",
            content="Devin is our AI agent. Powered by Devin AI from Cognition.",
        )
        issues: list = []
        check_brand_consistency(knowledge, [source], issues)
        assert len(issues) == 1
        assert issues[0].issue_type == IssueType.brand_mismatch
        assert issues[0].severity == IssueSeverity.low

    def test_single_mention_does_not_trigger(self):
        knowledge = [
            _minimal_knowledge("Windsurf", "https://windsurf.com"),
            _minimal_knowledge("Cursor", "https://cursor.com"),
        ]
        source = SourceEvidence(
            competitor_name="Windsurf",
            source_type=SourceType.official_website,
            url="https://windsurf.com/blog",
            title="Windsurf blog",
            content="Some developers prefer Cursor. Windsurf offers a different approach.",
        )
        issues: list = []
        check_brand_consistency(knowledge, [source], issues)
        assert len(issues) == 0

    def test_correct_competitor_content_not_flagged(self):
        knowledge = [_minimal_knowledge("Cursor", "https://cursor.com")]
        source = SourceEvidence(
            competitor_name="Cursor",
            source_type=SourceType.pricing_page,
            url="https://cursor.com/pricing",
            title="Cursor Pricing",
            content="Cursor Pro plan. Cursor Enterprise. Cursor for teams.",
        )
        issues: list = []
        check_brand_consistency(knowledge, [source], issues)
        assert len(issues) == 0

    def test_review_comparison_mentions_other_competitor_not_flagged(self):
        knowledge = [
            _minimal_knowledge("Windsurf", "https://windsurf.com"),
            _minimal_knowledge("Cursor", "https://cursor.com"),
        ]
        source = SourceEvidence(
            competitor_name="Windsurf",
            source_type=SourceType.review,
            url="https://reddit.example/windsurf-vs-cursor",
            title="Switched from Cursor to Windsurf",
            content=(
                "Cursor is faster for tab completion. Cursor pricing pushed me "
                "to Windsurf, where Cascade is good enough."
            ),
        )
        issues: list = []
        check_brand_consistency(knowledge, [source], issues)
        assert issues == []
