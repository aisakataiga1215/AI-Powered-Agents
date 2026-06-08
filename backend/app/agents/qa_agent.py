"""QAAgent.

Performs rule-based quality checks on a draft report and the structured
knowledge that produced it.

The MVP intentionally uses deterministic checks rather than an LLM so the
QA decision is reproducible, fast, and explainable. Each violation
becomes a :class:`QAIssue` with an explicit ``target_agent`` so the
LangGraph router can dispatch rework precisely.
"""

import re
import time
import uuid

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.schemas.claim import Claim
from app.schemas.knowledge import CompetitorKnowledge
from app.schemas.qa import IssueSeverity, IssueType, QAIssue, QAResult
from app.schemas.report import CompetitiveReport
from app.schemas.source import SourceEvidence, SourceType
from app.schemas.trace import AgentRun, AgentRunStatus
from app.services import coverage_evaluator, qa_service, trace_service

logger = get_logger(__name__)

_HIGH_PENALTY = 15
_MEDIUM_PENALTY = 5
_PASS_THRESHOLD = 80
_MAX_CLAIM_PREVIEW = 80
_PRICE_PATTERN = re.compile(r"\$\s?(\d+(?:\.\d+)?)")


# ---------------------------------------------------------------------------
# Individual rule checks
# ---------------------------------------------------------------------------


def check_required_sections(
    report: CompetitiveReport,
    issues: list[QAIssue],
) -> None:
    """Ensure all required top-level report sections are populated."""
    if not report.executive_summary:
        issues.append(
            QAIssue(
                severity=IssueSeverity.high,
                issue_type=IssueType.missing_report_section,
                target_agent="WriterAgent",
                message="Executive summary is missing",
                suggested_action="WriterAgent must generate executive_summary",
            )
        )
    if not report.competitor_overview:
        issues.append(
            QAIssue(
                severity=IssueSeverity.high,
                issue_type=IssueType.missing_report_section,
                target_agent="WriterAgent",
                message="Competitor overview is missing",
                suggested_action="WriterAgent must include competitor_overview",
            )
        )
    if not report.feature_comparison:
        issues.append(
            QAIssue(
                severity=IssueSeverity.medium,
                issue_type=IssueType.missing_report_section,
                target_agent="WriterAgent",
                message="Feature comparison table is missing",
                suggested_action=(
                    "WriterAgent must produce a feature_comparison dict "
                    "covering all competitors"
                ),
            )
        )
    if not report.pricing_comparison:
        issues.append(
            QAIssue(
                severity=IssueSeverity.medium,
                issue_type=IssueType.missing_report_section,
                target_agent="WriterAgent",
                message="Pricing comparison table is missing",
                suggested_action=(
                    "WriterAgent must produce a pricing_comparison dict "
                    "covering all competitors"
                ),
            )
        )
    if not report.swot_comparison:
        issues.append(
            QAIssue(
                severity=IssueSeverity.medium,
                issue_type=IssueType.missing_report_section,
                target_agent="WriterAgent",
                message="SWOT comparison is missing",
                suggested_action=(
                    "WriterAgent must produce swot_comparison entries for "
                    "every competitor"
                ),
            )
        )
    if not report.strategic_recommendations:
        issues.append(
            QAIssue(
                severity=IssueSeverity.high,
                issue_type=IssueType.missing_report_section,
                target_agent="WriterAgent",
                message="Strategic recommendations are missing",
                suggested_action=(
                    "WriterAgent must propose at least 2 strategic_recommendations"
                ),
            )
        )


def check_competitor_profiles(
    report: CompetitiveReport,
    issues: list[QAIssue],
) -> None:
    """Each competitor must have a populated product profile."""
    for ck in report.competitor_overview:
        label = ck.competitor_name or ck.competitor_id or "<unknown>"
        if not ck.product_profile or not ck.product_profile.name:
            issues.append(
                QAIssue(
                    severity=IssueSeverity.high,
                    issue_type=IssueType.missing_required_field,
                    target_agent="AnalystAgent",
                    message=f"Missing product_profile.name for {label}",
                    suggested_action=(
                        f"AnalystAgent must extract product_profile for {label}"
                    ),
                )
            )
            continue
        if (
            ck.product_profile.positioning is None
            or not ck.product_profile.positioning.text.strip()
        ):
            issues.append(
                QAIssue(
                    severity=IssueSeverity.medium,
                    issue_type=IssueType.missing_required_field,
                    target_agent="AnalystAgent",
                    message=f"Missing positioning claim for {label}",
                    suggested_action=(
                        f"AnalystAgent must add positioning claim for {label}"
                    ),
                )
            )


def check_pricing_exists(
    report: CompetitiveReport,
    sources: list[SourceEvidence],
    goals: list[str],
    issues: list[QAIssue],
) -> None:
    """When pricing_analysis is requested, every competitor needs pricing data.

    Splits the failure mode by who can actually fix it:

    - **No pricing_page source present** → blame the CollectorAgent. The
      analyst could not have extracted pricing without one. The rework
      hint that comes out of this issue is what flips
      ``demo_scenario=missing_pricing_source`` back to a full collection
      on retry.
    - **Pricing source exists but pricing_model.plans is empty** → blame
      the AnalystAgent for missing the extraction. Sending this to the
      collector would loop forever.
    """
    if "pricing_analysis" not in goals:
        return
    pricing_sources_by_comp: dict[str, list[SourceEvidence]] = {}
    for src in sources:
        if src.source_type is SourceType.pricing_page:
            pricing_sources_by_comp.setdefault(src.competitor_name, []).append(src)

    for ck in report.competitor_overview:
        label = ck.competitor_name or ck.competitor_id or "<unknown>"
        has_pricing_source = bool(
            pricing_sources_by_comp.get(ck.competitor_name)
        )
        has_pricing_plans = bool(
            ck.pricing_model and ck.pricing_model.plans
        )
        if not has_pricing_source:
            issues.append(
                QAIssue(
                    severity=IssueSeverity.high,
                    issue_type=IssueType.missing_pricing,
                    target_agent="CollectorAgent",
                    message=f"No pricing_page source for {label}",
                    suggested_action=(
                        f"CollectorAgent must collect the official pricing "
                        f"page for {label}"
                    ),
                )
            )
            continue
        if not has_pricing_plans:
            issues.append(
                QAIssue(
                    severity=IssueSeverity.high,
                    issue_type=IssueType.missing_pricing,
                    target_agent="AnalystAgent",
                    message=f"Pricing plans not extracted for {label}",
                    suggested_action=(
                        f"AnalystAgent must extract pricing_model.plans "
                        f"from the pricing_page source for {label}"
                    ),
                )
            )


def check_feature_tree(
    report: CompetitiveReport,
    issues: list[QAIssue],
) -> None:
    """Every competitor needs at least one feature category with features."""
    for ck in report.competitor_overview:
        label = ck.competitor_name or ck.competitor_id or "<unknown>"
        if not ck.feature_tree or not any(cat.features for cat in ck.feature_tree):
            issues.append(
                QAIssue(
                    severity=IssueSeverity.medium,
                    issue_type=IssueType.missing_required_field,
                    target_agent="AnalystAgent",
                    message=f"Feature tree is empty for {label}",
                    suggested_action=(
                        f"AnalystAgent must extract feature_tree for {label}"
                    ),
                )
            )


def _extract_prices(text: str) -> set[str]:
    """Return the set of dollar amounts (as bare numeric strings) in ``text``.

    Matches ``$20``, ``$ 20``, ``$20.00`` etc. Strips whitespace so
    ``"$20"`` and ``"$ 20"`` are equivalent. Returns ``set()`` if no
    matches.
    """
    if not text:
        return set()
    return {match.group(1) for match in _PRICE_PATTERN.finditer(text)}


def check_pricing_consistency(
    report: CompetitiveReport,
    issues: list[QAIssue],
) -> None:
    """Flag mismatches between ``pricing_model.plans`` and ``pricing_comparison``.

    The analyst's ``pricing_model`` is the structured source of truth.
    The writer's ``pricing_comparison`` should restate the same numbers
    in summary form. A dollar amount in the comparison that doesn't
    appear in any plan is almost always a writer hallucination — flag
    it so QA can route a writer rework rather than shipping a report
    with contradictory numbers.
    """
    if not report.pricing_comparison:
        return
    plans_by_competitor: dict[str, set[str]] = {}
    for ck in report.competitor_overview:
        if not ck.pricing_model or not ck.pricing_model.plans:
            continue
        prices: set[str] = set()
        for plan in ck.pricing_model.plans:
            prices.update(_extract_prices(plan.price))
        plans_by_competitor[ck.competitor_name] = prices

    for competitor_name, summary in report.pricing_comparison.items():
        # Skip if we have no structured prices to compare against.
        plan_prices = plans_by_competitor.get(competitor_name)
        if not plan_prices:
            continue
        summary_text = summary if isinstance(summary, str) else str(summary)
        summary_prices = _extract_prices(summary_text)
        if not summary_prices:
            continue
        mismatched = sorted(summary_prices - plan_prices)
        if mismatched:
            issues.append(
                QAIssue(
                    severity=IssueSeverity.high,
                    issue_type=IssueType.pricing_inconsistency,
                    target_agent="WriterAgent",
                    message=(
                        f"pricing_comparison for {competitor_name} mentions "
                        f"${', $'.join(mismatched)} but pricing_model.plans "
                        f"only lists ${', $'.join(sorted(plan_prices))}"
                    ),
                    suggested_action=(
                        f"WriterAgent must align pricing_comparison['{competitor_name}'] "
                        "with the numbers in pricing_model.plans, or correct "
                        "pricing_model if the analyst missed a plan"
                    ),
                )
            )


def _walk_report_claims(report: CompetitiveReport) -> list[Claim]:
    """Collect every claim that should be checked for evidence coverage."""
    claims: list[Claim] = []
    claims.extend(report.executive_summary)
    claims.extend(report.strategic_recommendations)
    for ck in report.competitor_overview:
        if ck.product_profile:
            if ck.product_profile.positioning is not None:
                claims.append(ck.product_profile.positioning)
            claims.extend(ck.product_profile.target_users)
        if ck.pricing_model and ck.pricing_model.summary is not None:
            claims.append(ck.pricing_model.summary)
        if ck.user_feedback_summary:
            claims.extend(ck.user_feedback_summary.positive_points)
            claims.extend(ck.user_feedback_summary.negative_points)
        if ck.swot:
            claims.extend(ck.swot.strengths)
            claims.extend(ck.swot.weaknesses)
            claims.extend(ck.swot.opportunities)
            claims.extend(ck.swot.threats)
    return claims


def _preview(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= _MAX_CLAIM_PREVIEW:
        return text
    return text[:_MAX_CLAIM_PREVIEW] + "..."


def check_evidence_coverage(
    report: CompetitiveReport,
    source_ids: set[str],
    issues: list[QAIssue],
) -> None:
    """Every non-hypothesis claim needs at least one valid evidence source_id."""
    for claim in _walk_report_claims(report):
        if not claim.is_hypothesis and not claim.evidence:
            issues.append(
                QAIssue(
                    severity=IssueSeverity.high,
                    issue_type=IssueType.missing_citation_in_report,
                    target_agent="WriterAgent",
                    message=(
                        f"Claim has no evidence: '{_preview(claim.text)}'"
                    ),
                    suggested_action=(
                        "WriterAgent must bind source_ids to all "
                        "non-hypothesis claims, or mark them is_hypothesis=true"
                    ),
                )
            )
        for evidence_id in claim.evidence:
            if evidence_id not in source_ids:
                issues.append(
                    QAIssue(
                        severity=IssueSeverity.medium,
                        issue_type=IssueType.weak_evidence,
                        target_agent="AnalystAgent",
                        message=(
                            f"Claim references unknown source_id '{evidence_id}'"
                        ),
                        suggested_action=(
                            "Verify source ids match collected sources; "
                            "do not invent source ids"
                        ),
                    )
                )


def check_source_list(
    report: CompetitiveReport,
    issues: list[QAIssue],
) -> None:
    """The report must include a non-empty source_list."""
    if not report.source_list:
        issues.append(
            QAIssue(
                severity=IssueSeverity.high,
                issue_type=IssueType.missing_source,
                target_agent="CollectorAgent",
                message="Report source_list is empty",
                suggested_action=(
                    "CollectorAgent must provide sources and WriterAgent must "
                    "populate source_list"
                ),
            )
        )


def check_source_coverage(
    sources: list[SourceEvidence],
    goals: list[str],
    issues: list[QAIssue],
) -> None:
    """Flag per-competitor source-coverage gaps that conflict with requested goals.

    Generates one issue per competitor that is missing a required source type.
    This is distinct from ``check_pricing_exists`` (which checks report
    content); this check fires earlier and targets the CollectorAgent so it
    can be re-run with better coverage before the analyst even runs.
    """
    coverage_map = coverage_evaluator.evaluate_per_competitor(sources)
    for competitor_name, cov in coverage_map.items():
        if "pricing_analysis" in goals and not cov.pricing:
            issues.append(
                QAIssue(
                    severity=IssueSeverity.high,
                    issue_type=IssueType.missing_pricing_source,
                    target_agent="CollectorAgent",
                    message=(
                        f"Pricing analysis requested but no pricing_page source "
                        f"found for {competitor_name}."
                    ),
                    suggested_action=(
                        f"Re-run collector targeting {competitor_name} pricing page."
                    ),
                )
            )
        if "feature_comparison" in goals and not cov.features_or_docs:
            issues.append(
                QAIssue(
                    severity=IssueSeverity.medium,
                    issue_type=IssueType.missing_features_source,
                    target_agent="CollectorAgent",
                    message=(
                        f"Feature comparison requested but no features/docs source "
                        f"found for {competitor_name}."
                    ),
                    suggested_action=(
                        f"Re-run collector targeting {competitor_name} features or "
                        "documentation page."
                    ),
                )
            )


_BAD_CONTENT_SIGNALS: tuple[str, ...] = (
    "discord",
    "cloudflare",
    "just a moment",
    "verify you are human",
    "access denied",
    "forbidden",
    "login required",
    "sign in to continue",
)
_PRICING_KEYWORDS: tuple[str, ...] = (
    "price",
    "pricing",
    "per month",
    "per user",
    "$/mo",
    "plan",
    "subscription",
    "free tier",
    "enterprise",
)
_FEATURES_KEYWORDS: tuple[str, ...] = (
    "feature",
    "product",
    "capability",
    "what you get",
    "how it works",
    "built for",
    "includes",
)
_QA_CONTENT_PREVIEW = 500


def check_source_quality(
    sources: list[SourceEvidence],
    issues: list[QAIssue],
) -> None:
    """Detect sources whose declared type contradicts their actual content.

    Severity tiering:
    - high: content has explicit bad signals (Discord, captcha, login wall)
    - medium: content is non-empty but lacks keywords expected for the declared type
    Only checks pricing_page and features_page sources with non-empty content.
    """
    checked_types = (SourceType.pricing_page, SourceType.features_page)
    for source in sources:
        if source.source_type not in checked_types:
            continue
        if not source.content:
            continue  # skip sources with no crawled content

        combined = (source.title + " " + source.content[:_QA_CONTENT_PREVIEW]).lower()
        keywords = (
            _PRICING_KEYWORDS
            if source.source_type is SourceType.pricing_page
            else _FEATURES_KEYWORDS
        )
        if any(kw in combined for kw in keywords):
            continue  # content matches declared type — no issue

        if any(sig in combined for sig in _BAD_CONTENT_SIGNALS):
            severity = IssueSeverity.high
            detail = "has blocked/unrelated content"
        else:
            severity = IssueSeverity.medium
            detail = (
                f"has weak content (no {source.source_type.value} keywords found)"
            )

        issues.append(
            QAIssue(
                severity=severity,
                issue_type=IssueType.weak_source_quality,
                target_agent="CollectorAgent",
                message=(
                    f"{source.source_type.value} source '{source.title}' "
                    f"at {source.url} {detail}"
                ),
                suggested_action=(
                    f"Re-collect a valid {source.source_type.value} source "
                    f"for {source.competitor_name}"
                ),
            )
        )


# ---------------------------------------------------------------------------
# Brand consistency check
# ---------------------------------------------------------------------------

# Known brand families: maps a competitor name (lowercase) to related brand names
# that may appear in its sources and should be flagged as advisory.
_PRODUCT_BRAND_MAP: dict[str, frozenset] = {
    "windsurf": frozenset({"cognition", "devin"}),
}

_BRAND_MENTION_THRESHOLD = 2


def check_brand_consistency(
    knowledge: list[CompetitorKnowledge],
    sources: list[SourceEvidence],
    issues: list[QAIssue],
) -> None:
    """Advisory check: flag sources that prominently mention a different product brand.

    Checks against other project competitor names and a static known-brand map
    (e.g. Windsurf → Devin/Cognition). Severity: low — does not affect score.
    Threshold: >= 2 mentions in title + first 500 chars of content.
    One issue per source max.
    """
    competitor_names = {k.competitor_name.lower() for k in knowledge}

    for source in sources:
        expected = source.competitor_name.lower()
        preview = (source.title + " " + (source.content or "")[:500]).lower()

        extra_brands = _PRODUCT_BRAND_MAP.get(expected, frozenset())
        brands_to_check = (competitor_names | extra_brands) - {expected}

        for brand in brands_to_check:
            mentions = preview.count(brand)
            if mentions >= _BRAND_MENTION_THRESHOLD:
                issues.append(
                    QAIssue(
                        severity=IssueSeverity.low,
                        issue_type=IssueType.brand_mismatch,
                        target_agent="CollectorAgent",
                        message=(
                            f"Source for '{source.competitor_name}' mentions "
                            f"'{brand}' {mentions}x — may reflect rebranding "
                            f"or wrong source page"
                        ),
                        suggested_action=(
                            f"Verify this source is the correct page for "
                            f"{source.competitor_name}"
                        ),
                    )
                )
                break  # one issue per source max


def check_custom_dimensions(
    report: CompetitiveReport,
    custom_dimensions: list[str],
) -> list[QAIssue]:
    """Advisory check: ensure custom dimensions appear in the report."""
    if not custom_dimensions:
        return []
    content = (report.markdown_content or "").lower()
    present = set(report.custom_dimension_analysis.keys())
    issues: list[QAIssue] = []
    for dim in custom_dimensions:
        if dim.lower() not in content and dim not in present:
            issues.append(
                QAIssue(
                    severity=IssueSeverity.medium,
                    issue_type=IssueType.missing_custom_dimension_coverage,
                    target_agent="WriterAgent",
                    message=f"Custom dimension '{dim}' not found in report",
                    suggested_action=f"Address '{dim}' in the analysis",
                )
            )
    return issues


def check_scoring_rationale(
    report: CompetitiveReport,
    analysis_purpose: str,
) -> list[QAIssue]:
    """Advisory check: ensure scoring sections are present for non-general purposes."""
    if analysis_purpose == "general":
        return []
    issues: list[QAIssue] = []
    if analysis_purpose == "choose_product":
        if not report.competitor_scores:
            issues.append(
                QAIssue(
                    severity=IssueSeverity.medium,
                    issue_type=IssueType.missing_score_rationale,
                    target_agent="WriterAgent",
                    message="competitor_scores missing for choose_product",
                    suggested_action="Add competitor scoring matrix",
                )
            )
        else:
            for name, cs in report.competitor_scores.items():
                empty_rationale = [d for d in cs.dimensions if not d.rationale]
                if empty_rationale:
                    issues.append(
                        QAIssue(
                            severity=IssueSeverity.medium,
                            issue_type=IssueType.missing_score_rationale,
                            target_agent="WriterAgent",
                            message=f"Dimension scores for '{name}' missing rationale",
                            suggested_action="Add rationale for each dimension score",
                        )
                    )
    elif analysis_purpose == "build_product":
        if not report.opportunity_score:
            issues.append(
                QAIssue(
                    severity=IssueSeverity.medium,
                    issue_type=IssueType.missing_score_rationale,
                    target_agent="WriterAgent",
                    message="opportunity_score missing for build_product",
                    suggested_action="Add opportunity scoring matrix",
                )
            )
    return issues


def check_pm_sections(report: CompetitiveReport) -> list[QAIssue]:
    """Advisory check: ensure PM-framework sections are present."""
    issues: list[QAIssue] = []
    if not report.market_background or not report.market_background.market_overview:
        issues.append(
            QAIssue(
                severity=IssueSeverity.medium,
                issue_type=IssueType.missing_market_background,
                target_agent="WriterAgent",
                message="market_background section absent or empty",
                suggested_action="Add market overview, trends, drivers, and challenges",
            )
        )
    if not report.feature_insights or not report.feature_insights.table_stakes:
        issues.append(
            QAIssue(
                severity=IssueSeverity.medium,
                issue_type=IssueType.missing_feature_insights,
                target_agent="WriterAgent",
                message="feature_insights section absent or table_stakes empty",
                suggested_action="Identify table-stakes features, differentiators, and gaps",
            )
        )
    if not report.operation_monetization or not report.operation_monetization.gtm_profiles:
        issues.append(
            QAIssue(
                severity=IssueSeverity.medium,
                issue_type=IssueType.missing_operation_monetization,
                target_agent="WriterAgent",
                message="operation_monetization section absent or no GTM profiles",
                suggested_action="Add GTM profiles and AARRR notes for each competitor",
            )
        )
    return issues
def _build_trace_output(result: QAResult, issues: list[QAIssue]) -> dict:
    """Build the trace output dict for a completed QAAgent run.

    Extracted as a standalone function so it can be unit-tested without a
    database. Use ``==`` for enum comparisons (safer than ``is`` for str enums).
    """
    return {
        "qa_result_id": result.qa_result_id,
        "passed": result.passed,
        "score": result.score,
        "issues": [i.model_dump(mode="json") for i in issues],
        "issue_count": len(issues),
        "high_severity_count": sum(
            1 for i in issues if i.severity == IssueSeverity.high
        ),
        "medium_severity_count": sum(
            1 for i in issues if i.severity == IssueSeverity.medium
        ),
        "low_severity_count": sum(
            1 for i in issues if i.severity == IssueSeverity.low
        ),
        "blocking_issue_count": sum(
            1
            for i in issues
            if i.severity in (IssueSeverity.high, IssueSeverity.medium)
        ),
        "advisory_count": sum(
            1 for i in issues if i.severity == IssueSeverity.low
        ),
    }


def _score_issues(issues: list[QAIssue]) -> int:
    score = 100
    for issue in issues:
        if issue.severity is IssueSeverity.high:
            score -= _HIGH_PENALTY
        elif issue.severity is IssueSeverity.medium:
            score -= _MEDIUM_PENALTY
    return max(score, 0)


def _has_high_severity(issues: list[QAIssue]) -> bool:
    return any(i.severity is IssueSeverity.high for i in issues)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(
    db: Session,
    project_id: str,
    report: CompetitiveReport,
    knowledge: list[CompetitorKnowledge],
    sources: list[SourceEvidence],
    goals: list[str],
    analysis_purpose: str = "general",
    custom_dimensions: list[str] | None = None,
) -> QAResult:
    """Run rule-based QA checks and persist the resulting :class:`QAResult`."""
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    start = time.time()

    agent_run = AgentRun(
        agent_run_id=run_id,
        project_id=project_id,
        agent_name="QAAgent",
        input={
            "report_id": report.report_id,
            "knowledge_count": len(knowledge),
            "source_count": len(sources),
            "goals": goals,
            "analysis_purpose": analysis_purpose,
            "custom_dimensions": custom_dimensions or [],
        },
        status=AgentRunStatus.running,
    )
    trace_service.save_agent_run(db, agent_run)

    try:
        issues: list[QAIssue] = []
        known_source_ids: set[str] = {s.source_id for s in sources}
        known_source_ids.update(s.source_id for s in report.source_list)

        check_required_sections(report, issues)
        check_competitor_profiles(report, issues)
        check_pricing_exists(report, sources, goals, issues)
        check_pricing_consistency(report, issues)
        check_feature_tree(report, issues)
        check_evidence_coverage(report, known_source_ids, issues)
        check_source_list(report, issues)
        check_source_coverage(sources, goals, issues)
        check_source_quality(sources, issues)
        check_brand_consistency(knowledge, sources, issues)
        # Advisory-only checks — medium severity, never change pass/fail threshold.
        issues.extend(check_custom_dimensions(report, custom_dimensions or []))
        issues.extend(check_scoring_rationale(report, analysis_purpose))
        issues.extend(check_pm_sections(report))

        score = _score_issues(issues)
        passed = score >= _PASS_THRESHOLD and not _has_high_severity(issues)

        result = QAResult(
            project_id=project_id,
            passed=passed,
            score=score,
            issues=issues,
        )
        qa_service.save_qa_result(db, result)

        elapsed_ms = int((time.time() - start) * 1000)
        trace_service.update_agent_run(
            db,
            run_id,
            status=AgentRunStatus.success,
            output=_build_trace_output(result, issues),
            latency_ms=elapsed_ms,
        )
        logger.info(
            "QAAgent: project %s scored %d, passed=%s, %d issues",
            project_id,
            score,
            passed,
            len(issues),
        )
        return result

    except Exception as exc:
        elapsed_ms = int((time.time() - start) * 1000)
        trace_service.update_agent_run(
            db,
            run_id,
            status=AgentRunStatus.failed,
            error_message=str(exc),
            latency_ms=elapsed_ms,
        )
        logger.error("QAAgent failed: %s", exc)
        raise
