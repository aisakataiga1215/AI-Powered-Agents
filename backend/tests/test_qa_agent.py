"""QAAgent rule-based checks.

These tests exercise the deterministic QA rules without invoking the
LLM. They cover:

- Missing required report sections
- Missing competitor product profile
- Missing pricing data when pricing_analysis is a goal
- Missing feature tree
- Claims without evidence or with unknown source ids
- Empty source list
- Scoring math
"""

from app.agents import qa_agent
from app.schemas.claim import Claim
from app.schemas.knowledge import (
    CompetitorKnowledge,
    FeatureCategory,
    FeatureItem,
    PricingModel,
    PricingPlan,
    ProductProfile,
    SWOTAnalysis,
)
from app.schemas.qa import IssueSeverity, IssueType, QAIssue
from app.schemas.report import CompetitiveReport
from app.schemas.source import Reliability, SourceEvidence, SourceType


def _make_source(source_id: str = "src_aaaaaa01") -> SourceEvidence:
    return SourceEvidence(
        source_id=source_id,
        competitor_name="Cursor",
        source_type=SourceType.official_website,
        url="https://cursor.com",
        title="Cursor",
        snippet="",
        content="",
        reliability=Reliability.high,
    )


def _make_full_competitor(source_id: str = "src_aaaaaa01") -> CompetitorKnowledge:
    return CompetitorKnowledge(
        competitor_id="comp_1",
        competitor_name="Cursor",
        product_profile=ProductProfile(
            name="Cursor",
            website="https://cursor.com",
            positioning=Claim(text="AI code editor", evidence=[source_id]),
        ),
        feature_tree=[
            FeatureCategory(
                category="AI Coding",
                features=[
                    FeatureItem(
                        name="Tab completion",
                        availability="available",
                        evidence=[source_id],
                    )
                ],
            )
        ],
        pricing_model=PricingModel(
            has_free_plan=True,
            plans=[PricingPlan(name="Pro", price="$20")],
        ),
        swot=SWOTAnalysis(
            strengths=[Claim(text="Strong UX", evidence=[source_id])],
        ),
        sources=[source_id],
    )


def _make_passing_report(source_id: str = "src_aaaaaa01") -> CompetitiveReport:
    return CompetitiveReport(
        project_id="proj_1",
        executive_summary=[Claim(text="Strong market", evidence=[source_id])],
        competitor_overview=[_make_full_competitor(source_id)],
        feature_comparison={"AI Coding": {"Cursor": "available"}},
        pricing_comparison={"Cursor": "$20/mo Pro"},
        swot_comparison={"Cursor": "Strong UX"},
        strategic_recommendations=[
            Claim(text="Bundle pricing", evidence=[source_id])
        ],
        source_list=[_make_source(source_id)],
    )


# ---------------------------------------------------------------------------
# Section checks
# ---------------------------------------------------------------------------


def test_check_required_sections_flags_missing_executive_summary():
    report = _make_passing_report()
    report.executive_summary = []
    issues: list[QAIssue] = []

    qa_agent.check_required_sections(report, issues)

    high_issues = [i for i in issues if i.severity is IssueSeverity.high]
    assert any(
        i.issue_type is IssueType.missing_report_section
        and "executive summary" in i.message.lower()
        for i in high_issues
    )


def test_check_required_sections_flags_missing_recommendations():
    report = _make_passing_report()
    report.strategic_recommendations = []
    issues: list[QAIssue] = []

    qa_agent.check_required_sections(report, issues)

    assert any(
        i.severity is IssueSeverity.high and "recommendations" in i.message.lower()
        for i in issues
    )


def test_check_required_sections_passes_clean_report():
    report = _make_passing_report()
    issues: list[QAIssue] = []
    qa_agent.check_required_sections(report, issues)
    assert issues == []


# ---------------------------------------------------------------------------
# Competitor profile
# ---------------------------------------------------------------------------


def test_check_competitor_profiles_flags_missing_profile():
    report = _make_passing_report()
    report.competitor_overview[0].product_profile = None
    issues: list[QAIssue] = []

    qa_agent.check_competitor_profiles(report, issues)

    assert any(
        i.severity is IssueSeverity.high
        and i.target_agent == "AnalystAgent"
        for i in issues
    )


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------


def test_check_pricing_flags_missing_source_targets_collector():
    """No pricing_page source for the competitor → blame CollectorAgent."""
    report = _make_passing_report()
    # Pricing model still populated, but we hand the rule no pricing sources.
    issues: list[QAIssue] = []

    qa_agent.check_pricing_exists(
        report, [_make_source()], ["pricing_analysis"], issues
    )

    matching = [
        i for i in issues
        if i.issue_type is IssueType.missing_pricing
        and i.target_agent == "CollectorAgent"
    ]
    assert matching, "expected a missing_pricing issue targeting CollectorAgent"


def test_check_pricing_flags_extraction_gap_targets_analyst():
    """Pricing source present but pricing_model empty → blame AnalystAgent."""
    report = _make_passing_report()
    report.competitor_overview[0].pricing_model = None
    pricing_source = SourceEvidence(
        source_id="src_pricing_01",
        competitor_name="Cursor",
        source_type=SourceType.pricing_page,
        url="https://cursor.com/pricing",
        title="Pricing",
        reliability=Reliability.high,
    )
    issues: list[QAIssue] = []

    qa_agent.check_pricing_exists(
        report, [pricing_source], ["pricing_analysis"], issues
    )

    assert any(
        i.issue_type is IssueType.missing_pricing
        and i.target_agent == "AnalystAgent"
        for i in issues
    )


def test_check_pricing_skipped_when_goal_absent():
    report = _make_passing_report()
    report.competitor_overview[0].pricing_model = None
    issues: list[QAIssue] = []

    qa_agent.check_pricing_exists(
        report, [], ["feature_comparison"], issues
    )

    assert issues == []


# ---------------------------------------------------------------------------
# Feature tree
# ---------------------------------------------------------------------------


def test_check_feature_tree_flags_empty_tree():
    report = _make_passing_report()
    report.competitor_overview[0].feature_tree = []
    issues: list[QAIssue] = []

    qa_agent.check_feature_tree(report, issues)

    assert any(
        i.issue_type is IssueType.missing_required_field
        and i.target_agent == "AnalystAgent"
        for i in issues
    )


# ---------------------------------------------------------------------------
# Evidence coverage
# ---------------------------------------------------------------------------


def test_check_evidence_coverage_flags_claim_without_evidence():
    report = _make_passing_report()
    report.executive_summary = [Claim(text="bad claim", evidence=[])]
    issues: list[QAIssue] = []

    qa_agent.check_evidence_coverage(report, {"src_aaaaaa01"}, issues)

    assert any(
        i.issue_type is IssueType.missing_citation_in_report
        and i.target_agent == "WriterAgent"
        for i in issues
    )


def test_check_evidence_coverage_allows_hypothesis_without_evidence():
    report = _make_passing_report()
    report.executive_summary = [
        Claim(text="might be", evidence=[], is_hypothesis=True)
    ]
    issues: list[QAIssue] = []

    qa_agent.check_evidence_coverage(report, {"src_aaaaaa01"}, issues)

    assert not any(
        i.issue_type is IssueType.missing_citation_in_report for i in issues
    )


def test_check_evidence_coverage_flags_unknown_source_id():
    report = _make_passing_report()
    report.executive_summary = [
        Claim(text="bad ref", evidence=["src_does_not_exist"])
    ]
    issues: list[QAIssue] = []

    qa_agent.check_evidence_coverage(report, {"src_aaaaaa01"}, issues)

    assert any(
        i.issue_type is IssueType.weak_evidence
        and i.target_agent == "AnalystAgent"
        for i in issues
    )


# ---------------------------------------------------------------------------
# Source list
# ---------------------------------------------------------------------------


def test_check_source_list_flags_empty_list():
    report = _make_passing_report()
    report.source_list = []
    issues: list[QAIssue] = []

    qa_agent.check_source_list(report, issues)

    assert any(
        i.issue_type is IssueType.missing_source
        and i.target_agent == "CollectorAgent"
        for i in issues
    )


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def test_score_issues_penalises_high_then_medium():
    issues = [
        QAIssue(
            severity=IssueSeverity.high,
            issue_type=IssueType.missing_source,
            target_agent="CollectorAgent",
            message="x",
        ),
        QAIssue(
            severity=IssueSeverity.medium,
            issue_type=IssueType.weak_evidence,
            target_agent="AnalystAgent",
            message="y",
        ),
    ]
    # 100 - 15 - 5 = 80
    assert qa_agent._score_issues(issues) == 80


def test_score_floor_zero():
    issues = [
        QAIssue(
            severity=IssueSeverity.high,
            issue_type=IssueType.missing_source,
            target_agent="CollectorAgent",
            message=f"i{n}",
        )
        for n in range(10)
    ]
    assert qa_agent._score_issues(issues) == 0


def test_has_high_severity_detects_any_high():
    issues = [
        QAIssue(
            severity=IssueSeverity.medium,
            issue_type=IssueType.weak_evidence,
            target_agent="AnalystAgent",
            message="m",
        ),
        QAIssue(
            severity=IssueSeverity.high,
            issue_type=IssueType.missing_source,
            target_agent="CollectorAgent",
            message="h",
        ),
    ]
    assert qa_agent._has_high_severity(issues) is True


def test_has_high_severity_false_when_only_medium():
    issues = [
        QAIssue(
            severity=IssueSeverity.medium,
            issue_type=IssueType.weak_evidence,
            target_agent="AnalystAgent",
            message="m",
        ),
    ]
    assert qa_agent._has_high_severity(issues) is False


# ---------------------------------------------------------------------------
# Pricing consistency
# ---------------------------------------------------------------------------


def test_check_pricing_consistency_passes_when_numbers_match():
    report = _make_passing_report()
    # _make_full_competitor uses $20 Pro; pricing_comparison says "$20/mo Pro".
    issues: list[QAIssue] = []
    qa_agent.check_pricing_consistency(report, issues)
    assert issues == []


def test_check_pricing_consistency_flags_writer_hallucination():
    """A dollar amount in pricing_comparison that's absent from
    pricing_model.plans is a writer hallucination — flag it as targeting
    WriterAgent, not the analyst.
    """
    report = _make_passing_report()
    # Plan says $20; writer summary claims $35. This is the bug type the
    # user flagged with Windsurf Teams.
    report.pricing_comparison = {"Cursor": "Pro plan at $35/month"}
    issues: list[QAIssue] = []

    qa_agent.check_pricing_consistency(report, issues)

    matching = [
        i for i in issues
        if i.issue_type is IssueType.pricing_inconsistency
        and i.target_agent == "WriterAgent"
    ]
    assert matching, "expected pricing_inconsistency targeting WriterAgent"
    assert "35" in matching[0].message
    assert "20" in matching[0].message


def test_check_pricing_consistency_ignores_competitors_without_plans():
    report = _make_passing_report()
    report.competitor_overview[0].pricing_model = None
    report.pricing_comparison = {"Cursor": "Pro at $99/mo"}
    issues: list[QAIssue] = []

    qa_agent.check_pricing_consistency(report, issues)

    # No structured plans to compare against → silent. The
    # missing-pricing rule covers this case.
    assert issues == []


def test_check_pricing_consistency_ignores_summaries_without_prices():
    report = _make_passing_report()
    report.pricing_comparison = {"Cursor": "Freemium with paid tier"}
    issues: list[QAIssue] = []

    qa_agent.check_pricing_consistency(report, issues)
    assert issues == []


def test_extract_prices_handles_variations():
    assert qa_agent._extract_prices("$20 and $35.50") == {"20", "35.50"}
    assert qa_agent._extract_prices("$ 10/mo") == {"10"}
    assert qa_agent._extract_prices("no prices here") == set()
    assert qa_agent._extract_prices("") == set()
