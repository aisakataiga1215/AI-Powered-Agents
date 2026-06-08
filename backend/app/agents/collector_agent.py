"""CollectorAgent.

Loads source evidence for each competitor and persists it. Supports two
collection modes controlled by ``data_mode``:

- ``"demo"``: Reads pre-canned fixture data from ``scripts/demo_fixtures/``
  (deterministic, no network required). Fixture files are primary sources,
  not fallback.
- ``"live_with_fallback"``: Probes industry-specific candidate paths on the
  competitor's root domain; falls back to demo fixtures per-competitor when
  live coverage is insufficient.

Each invocation is recorded as an :class:`AgentRun` so the frontend
trace timeline can replay the execution.
"""

import time
import uuid
from dataclasses import dataclass, field
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.source import Reliability, SourceEvidence, SourceType
from app.schemas.trace import AgentRun, AgentRunStatus
from app.services import (
    coverage_evaluator,
    crawler_service,
    source_classifier,
    source_discovery,
    source_service,
    trace_service,
)
from app.services.coverage_evaluator import WEAK_THRESHOLD

logger = get_logger(__name__)

_OFFICIAL_TYPES = {
    SourceType.official_website,
    SourceType.pricing_page,
    SourceType.docs,
    SourceType.features_page,
    SourceType.security,
    SourceType.privacy,
}


@dataclass
class _CollectionResult:
    """Per-competitor collection outcome for live_with_fallback mode."""

    sources: list = field(default_factory=list)
    failed_urls: list = field(default_factory=list)
    attempted_urls: list = field(default_factory=list)
    # Fields below only meaningful for live_with_fallback:
    live_source_count: int = 0
    fallback_attempted: bool = False   # coverage < WEAK_THRESHOLD or no candidate URLs
    fallback_used: bool = False        # demo sources were actually merged
    fallback_available: bool = False   # fixture file exists on disk
    fallback_source_count: int = 0     # number of merged demo sources


def _hints_request_pricing(rework_hints: list[str] | None) -> bool:
    """Return True when any rework hint asks for pricing data."""
    if not rework_hints:
        return False
    return any("pricing" in (hint or "").lower() for hint in rework_hints)


def _should_include_pricing(
    competitor_name: str,
    rework_hints: list[str] | None,
) -> bool:
    """Decide whether to include pricing_page sources for this competitor."""
    if settings.demo_scenario != "missing_pricing_source":
        return True
    if competitor_name.strip().lower() != (
        settings.demo_withheld_pricing_competitor or ""
    ).strip().lower():
        return True
    return _hints_request_pricing(rework_hints)


def _assign_reliability(
    source_type: SourceType,
    source_domain: str,
    competitor_domain: str,
) -> Reliability:
    if source_type in _OFFICIAL_TYPES:
        return Reliability.high if source_domain == competitor_domain else Reliability.medium
    if source_type is SourceType.unknown:
        return Reliability.low
    return Reliability.medium  # blog, review, news


def _is_adequately_covered(sources: list[SourceEvidence]) -> bool:
    """Return True when a competitor's sources meet the quality threshold.

    Accepts if coverage score >= WEAK_THRESHOLD, or homepage + at least
    one content page (pricing or features/docs).
    """
    cov = coverage_evaluator.evaluate(sources)
    if cov.score >= WEAK_THRESHOLD:
        return True
    return bool(cov.homepage and (cov.pricing or cov.features_or_docs))


def _infer_drop_reason(stats: dict, data_mode: str) -> str:
    """Human-readable explanation for why a competitor was dropped."""
    if data_mode == "live_with_fallback":
        if stats.get("fallback_attempted") and not stats.get("fallback_available"):
            return "No demo fallback available"
        if stats.get("live_source_count", 0) == 0 and not stats.get("fallback_used"):
            return "Crawl failed — no usable sources"
    else:  # demo
        if stats.get("demo_source_count", 0) == 0:
            return "No demo fixture found"
    if stats.get("source_count", 0) == 0:
        return "No usable sources collected"
    return "Weak coverage — insufficient for analysis"


def _collect_live(
    competitor_name: str,
    website: str,
    project_id: str,
    competitor_id: str,
    industry_type: str = "general",
) -> _CollectionResult:
    """Crawl a competitor's website using industry-specific paths.

    Returns a ``_CollectionResult`` with full per-competitor stats.
    Fallback semantics (fallback_attempted/used/available) only apply
    in live_with_fallback mode and are recorded here for trace observability.
    """
    competitor_domain = urlparse(website).netloc
    candidate_urls = source_discovery.discover_pages(website, industry_type=industry_type)

    live_sources: list[SourceEvidence] = []
    failed_urls: list[str] = []

    if not candidate_urls:
        failed_urls.append(website)
    else:
        for url in candidate_urls:
            page = crawler_service.crawl_page(url)
            if page is None:
                failed_urls.append(url)
                continue

            source_domain = urlparse(page.url).netloc
            s_type = source_classifier.classify(page.url, page.title, page.content)
            reliability = _assign_reliability(s_type, source_domain, competitor_domain)

            live_sources.append(
                SourceEvidence(
                    project_id=project_id,
                    competitor_id=competitor_id,
                    competitor_name=competitor_name,
                    source_type=s_type,
                    url=page.url,
                    title=page.title,
                    snippet=page.snippet,
                    content=page.content,
                    reliability=reliability,
                    data_source="live",
                )
            )

    cov = coverage_evaluator.evaluate(live_sources)
    fallback_attempted = cov.score < WEAK_THRESHOLD or not candidate_urls

    # Side-effect-free check — only reads file presence.
    fallback_available = crawler_service.fixture_exists(competitor_name)

    fixture_sources: list[SourceEvidence] = []
    if fallback_attempted and fallback_available:
        logger.info(
            "CollectorAgent: weak live coverage for '%s' (score=%d), merging demo fallback",
            competitor_name,
            cov.score,
        )
        available_fixtures = crawler_service.load_demo_fixtures(
            competitor_name, include_pricing=True
        )
        covered_types: set[SourceType] = set()
        if cov.homepage:
            covered_types.add(SourceType.official_website)
        if cov.pricing:
            covered_types.add(SourceType.pricing_page)
        if cov.features_or_docs:
            covered_types.update([SourceType.features_page, SourceType.docs])
        if cov.security_or_privacy:
            covered_types.update([SourceType.security, SourceType.privacy])

        for s in available_fixtures:
            if s.source_type not in covered_types:
                s_copy = s.model_copy(update={
                    "data_source": "demo",
                    "project_id": project_id,
                    "competitor_id": competitor_id or s.competitor_id,
                })
                fixture_sources.append(s_copy)

    fallback_used = len(fixture_sources) > 0
    all_sources = live_sources + fixture_sources

    return _CollectionResult(
        sources=all_sources,
        failed_urls=failed_urls,
        attempted_urls=candidate_urls,
        live_source_count=len(live_sources),
        fallback_attempted=fallback_attempted,
        fallback_used=fallback_used,
        fallback_available=fallback_available,
        fallback_source_count=len(fixture_sources),
    )


def run(
    db: Session,
    project_id: str,
    competitors: list[dict],
    goals: list[str],
    rework_hints: list[str] | None = None,
    data_mode: str = "demo",
    industry_type: str = "general",
) -> list[SourceEvidence]:
    """Load source evidence for all competitors and persist them.

    Args:
        db: SQLAlchemy session.
        project_id: Owning project id.
        competitors: List of ``{"name": str, "url": str}`` dicts.
        goals: Analysis goals (e.g. ``["pricing_analysis"]``).
        rework_hints: Optional QA hints from a previous failed run.
        data_mode: ``"demo"`` or ``"live_with_fallback"``.
        industry_type: Industry context for source discovery path selection.

    Returns:
        List of :class:`SourceEvidence` ready for downstream agents.
    """
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    start = time.time()

    agent_run = AgentRun(
        agent_run_id=run_id,
        project_id=project_id,
        agent_name="CollectorAgent",
        input={
            "competitors": competitors,
            "goals": goals,
            "rework_hints": rework_hints or [],
            "demo_scenario": settings.demo_scenario,
            "data_mode": data_mode,
            "industry_type": industry_type,
        },
        status=AgentRunStatus.running,
    )
    trace_service.save_agent_run(db, agent_run)

    try:
        all_sources: list[SourceEvidence] = []
        withheld_competitors: list[str] = []
        collection_stats: dict[str, dict] = {}
        attempted_urls_by_competitor: dict[str, list[str]] = {}
        all_failed_urls: list[str] = []

        for comp in competitors:
            name = comp.get("name", "") if isinstance(comp, dict) else ""
            if not name:
                logger.warning(
                    "CollectorAgent: competitor entry missing name, skipping: %s",
                    comp,
                )
                continue

            if data_mode == "live_with_fallback":
                website = comp.get("url", "") if isinstance(comp, dict) else ""
                competitor_id = name.strip().lower().replace(" ", "_")
                result = _collect_live(
                    name, website, project_id, competitor_id, industry_type
                )
                all_failed_urls.extend(result.failed_urls)
                attempted_urls_by_competitor[name] = result.attempted_urls
                collection_stats[name] = {
                    "source_count": len(result.sources),
                    "live_source_count": result.live_source_count,
                    "fallback_attempted": result.fallback_attempted,
                    "fallback_used": result.fallback_used,
                    "fallback_available": result.fallback_available,
                    "fallback_source_count": result.fallback_source_count,
                }
                sources = result.sources
            else:
                # Demo mode — fixtures are primary sources, not fallback.
                include_pricing = _should_include_pricing(name, rework_hints)
                if not include_pricing:
                    withheld_competitors.append(name)
                    logger.info(
                        "CollectorAgent: demo_scenario=%s -> withholding pricing "
                        "for '%s' (hints=%s)",
                        settings.demo_scenario,
                        name,
                        rework_hints or [],
                    )
                sources = crawler_service.load_demo_fixtures(
                    name, include_pricing=include_pricing
                )
                if not sources:
                    logger.warning(
                        "CollectorAgent: no demo fixtures found for competitor '%s'",
                        name,
                    )
                for src in sources:
                    src.project_id = project_id
                    if not src.competitor_id:
                        src.competitor_id = name.strip().lower().replace(" ", "_")
                collection_stats[name] = {
                    "source_count": len(sources),
                    "demo_source_count": len(sources),
                    # fallback fields NOT set in demo mode
                }

            all_sources.extend(sources)

        if all_sources:
            source_service.save_sources(db, project_id, all_sources)

        # Coverage map for trace (used by frontend inferDropReason).
        coverage_by_competitor: dict = {}
        for comp_name, cov in coverage_evaluator.evaluate_per_competitor(all_sources).items():
            coverage_by_competitor[comp_name] = {
                "homepage": cov.homepage,
                "pricing": cov.pricing,
                "features_or_docs": cov.features_or_docs,
                "security_or_privacy": cov.security_or_privacy,
                "score": cov.score,
            }

        # Determine which competitors have adequate coverage for analysis.
        # sufficiently_collected_competitors is for observability and the
        # InsufficientDataView gate only — does NOT filter AnalystAgent input.
        sufficiently_collected: set[str] = set()
        for comp in competitors:
            comp_name = comp.get("name", "") if isinstance(comp, dict) else ""
            if not comp_name:
                continue
            comp_sources = [s for s in all_sources if s.competitor_name == comp_name]
            if _is_adequately_covered(comp_sources):
                sufficiently_collected.add(comp_name)

        dropped_competitors = [
            {
                "name": comp.get("name", "") if isinstance(comp, dict) else "",
                "url": comp.get("url", "") if isinstance(comp, dict) else "",
                "reason": _infer_drop_reason(
                    collection_stats.get(comp.get("name", ""), {}),
                    data_mode,
                ),
            }
            for comp in competitors
            if (comp.get("name", "") if isinstance(comp, dict) else "") not in sufficiently_collected
        ]

        elapsed_ms = int((time.time() - start) * 1000)
        trace_service.update_agent_run(
            db,
            run_id,
            status=AgentRunStatus.success,
            output={
                "data_mode": data_mode,
                "industry_type": industry_type,
                "source_count": len(all_sources),
                "failed_urls": all_failed_urls,
                "source_coverage_by_competitor": coverage_by_competitor,
                "collection_stats_by_competitor": collection_stats,
                "attempted_urls_by_competitor": attempted_urls_by_competitor,
                "requested_competitors": [
                    {"name": c.get("name", ""), "url": c.get("url", "")}
                    for c in competitors
                    if isinstance(c, dict)
                ],
                "sufficiently_collected_competitors": sorted(sufficiently_collected),
                "dropped_competitors": dropped_competitors,
                "sources": [s.source_id for s in all_sources],
                "competitors": [
                    c.get("name", "") if isinstance(c, dict) else ""
                    for c in competitors
                ],
                "withheld_pricing_competitors": withheld_competitors,
                "rework_hints_used": rework_hints or [],
            },
            latency_ms=elapsed_ms,
        )
        logger.info(
            "CollectorAgent: collected %d sources for project %s (data_mode=%s, industry=%s)",
            len(all_sources),
            project_id,
            data_mode,
            industry_type,
        )
        return all_sources

    except Exception as exc:
        elapsed_ms = int((time.time() - start) * 1000)
        trace_service.update_agent_run(
            db,
            run_id,
            status=AgentRunStatus.failed,
            error_message=str(exc),
            latency_ms=elapsed_ms,
        )
        logger.error("CollectorAgent failed: %s", exc)
        raise
