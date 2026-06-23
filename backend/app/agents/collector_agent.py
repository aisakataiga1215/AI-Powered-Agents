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
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse, urlencode, parse_qsl

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.source import Reliability, SourceEvidence, SourceType
from app.schemas.trace import AgentRun, AgentRunStatus, TokenUsage
from app.services import (
    coverage_evaluator,
    crawler_service,
    source_classifier,
    source_discovery,
    source_service,
    trace_service,
)
from app.services.coverage_evaluator import WEAK_THRESHOLD
from app.services.search_provider import create_search_provider
from app.services.search_service import SearchService, _SEARCH_MAX_URLS
from app.services.source_discovery import get_industry_max_pages
from app.utils.sanitizer import sanitize_text

# All user-supplied research inputs are free-form enough to contain contact
# details, names, or identifiers, so sanitize them before they become evidence.
_PII_RESEARCH_KINDS = {"survey", "interview", "questionnaire", "desk_research", "notes"}
_RELEVANCE_REVIEW_MAX_SOURCES = 30
_RELEVANCE_SOURCE_PREVIEW_CHARS = 900

logger = get_logger(__name__)

_OFFICIAL_TYPES = {
    SourceType.official_website,
    SourceType.pricing_page,
    SourceType.docs,
    SourceType.features_page,
    SourceType.security,
    SourceType.privacy,
}

_TRACKING_PARAMS: frozenset[str] = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid",
})

_KNOWN_FOLLOWUP_URLS: dict[str, tuple[str, ...]] = {
    "claude code": (
        "https://code.claude.com/docs/en/overview",
        "https://docs.anthropic.com/en/docs/claude-code/overview",
        "https://www.anthropic.com/pricing",
    ),
    "codex": (
        "https://developers.openai.com/codex",
        "https://platform.openai.com/docs/pricing",
        "https://openai.com/chatgpt/pricing",
    ),
}


def _normalize_url(url: str) -> str:
    """Canonical URL form for deduplication.

    Lowercases scheme/host, strips trailing slash from path, removes known
    tracking query params (utm_*, fbclid, gclid), preserves all others.
    """
    parsed = urlparse(url)
    filtered_qs = urlencode(
        [(k, v) for k, v in parse_qsl(parsed.query) if k not in _TRACKING_PARAMS]
    )
    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path.rstrip("/"),
        parsed.params,
        filtered_qs,
        "",  # drop fragment
    ))


def _deduplicate_urls(urls: list[str]) -> list[str]:
    """Preserve insertion order, remove semantically duplicate URLs."""
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        norm = _normalize_url(url)
        if norm not in seen:
            seen.add(norm)
            result.append(url)
    return result


def _build_json_llm() -> ChatOpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured; CollectorAgent relevance review skipped.")
    kwargs: dict[str, Any] = {
        "model": settings.default_model,
        "api_key": settings.openai_api_key,
        "temperature": 0,
        "model_kwargs": {"response_format": {"type": "json_object"}},
    }
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    if settings.llm_disable_thinking:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    return ChatOpenAI(**kwargs)


def _extract_token_usage(response: Any) -> TokenUsage:
    meta = getattr(response, "usage_metadata", None)
    if meta and isinstance(meta, dict):
        prompt = int(meta.get("input_tokens", 0))
        completion = int(meta.get("output_tokens", 0))
        total = int(meta.get("total_tokens", 0))
        cost = (
            prompt * settings.openai_input_price_per_1m
            + completion * settings.openai_output_price_per_1m
        ) / 1_000_000
        return TokenUsage(prompt_tokens=prompt, completion_tokens=completion, total_tokens=total, cost_usd=cost)
    resp_meta = getattr(response, "response_metadata", None) or {}
    usage = resp_meta.get("token_usage") or resp_meta.get("usage") or {}
    if usage:
        prompt = int(usage.get("prompt_tokens", 0))
        completion = int(usage.get("completion_tokens", 0))
        total = int(usage.get("total_tokens", 0))
        cost = (
            prompt * settings.openai_input_price_per_1m
            + completion * settings.openai_output_price_per_1m
        ) / 1_000_000
        return TokenUsage(prompt_tokens=prompt, completion_tokens=completion, total_tokens=total, cost_usd=cost)
    return TokenUsage()


def _review_source_relevance(
    sources: list[SourceEvidence],
    competitors: list[dict],
    industry_type: str,
) -> tuple[list[SourceEvidence], dict[str, dict], TokenUsage, str]:
    if not sources:
        return sources, {}, TokenUsage(), "not_run"
    if not settings.openai_api_key:
        return sources, {}, TokenUsage(), "skipped_no_api_key"
    try:
        competitor_names = [
            c.get("name", "")
            for c in competitors
            if isinstance(c, dict) and c.get("name")
        ]
        review_sources = sources[:_RELEVANCE_REVIEW_MAX_SOURCES]
        payload = {
            "industry_type": industry_type,
            "competitors": competitor_names,
            "sources": [
                {
                    "source_id": source.source_id,
                    "competitor_name": source.competitor_name,
                    "source_type": source.source_type.value,
                    "url": source.url,
                    "title": source.title,
                    "snippet": source.snippet,
                    "content_preview": (source.content or "")[:_RELEVANCE_SOURCE_PREVIEW_CHARS],
                }
                for source in review_sources
            ],
        }
        response = _build_json_llm().invoke([
            SystemMessage(
                content=(
                    "Classify whether each source is relevant to the named competitor and product analysis. "
                    "Return JSON only: {\"sources\":[{\"source_id\":\"...\",\"action\":\"keep|weak|skip_for_analysis\","
                    "\"reason\":\"...\"}]}. Use skip_for_analysis only for clearly unrelated pages."
                )
            ),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
        ])
        usage = _extract_token_usage(response)
        content = getattr(response, "content", "") or "{}"
        parsed = json.loads(content) if isinstance(content, str) else content
        decisions: dict[str, dict] = {}
        for item in (parsed.get("sources") if isinstance(parsed, dict) else []) or []:
            source_id = str(item.get("source_id") or "")
            if not source_id:
                continue
            action = item.get("action")
            if action not in {"keep", "weak", "skip_for_analysis"}:
                action = "weak"
            decisions[source_id] = {
                "action": action,
                "reason": str(item.get("reason") or "")[:300],
            }
        reviewed_ids = {source.source_id for source in review_sources}
        for source in sources:
            if source.source_id not in decisions:
                decisions[source.source_id] = {
                    "action": "keep" if source.source_id in reviewed_ids else "not_reviewed",
                    "reason": "" if source.source_id in reviewed_ids else "Relevance review source cap reached.",
                }
        analysis_sources = [
            source
            for source in sources
            if decisions.get(source.source_id, {}).get("action") != "skip_for_analysis"
        ]
        return analysis_sources, decisions, usage, "success"
    except Exception as exc:
        logger.warning("CollectorAgent relevance review failed: %s", exc)
        return sources, {}, TokenUsage(), "failed"


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
    # M15A URL observability fields
    selected_extra_urls: list = field(default_factory=list)
    silent_search_urls: list = field(default_factory=list)
    custom_dimension_urls: list = field(default_factory=list)
    rejected_extra_urls: list = field(default_factory=list)


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


def _slug(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _custom_dimension_search_hints(custom_dimensions: list[str] | None) -> list[str]:
    if not custom_dimensions:
        return []
    hints: list[str] = []
    for dim in custom_dimensions:
        text = str(dim or "").strip()
        if not text:
            continue
        lower = text.lower()
        mapped: list[str] = []
        if "隐私" in text or "privacy" in lower:
            mapped.append("privacy data retention training policy")
        if "安全" in text or "合规" in text or "security" in lower or "compliance" in lower:
            mapped.append("security compliance SSO audit SOC ISO")
        if "本地" in text or "私有" in text or "部署" in text or "on-prem" in lower or "self-host" in lower:
            mapped.append("on-prem self-hosted local deployment enterprise")
        if "企业" in text or "enterprise" in lower:
            mapped.append("enterprise SSO admin audit security")
        # Always keep the user's original dimension. Custom dimensions can be
        # open-ended (for example "multi-agent"), so preset mappings are only
        # query expansion, not a closed taxonomy.
        hints.append(text)
        hints.append(f"{text} capabilities documentation")
        hints.extend(mapped)
    return list(dict.fromkeys(hints))


def _build_manual_sources(
    project_id: str,
    competitors: list[dict],
    research_inputs: list[dict] | None,
) -> list[SourceEvidence]:
    """Convert user-supplied surveys/interviews/notes into traceable evidence.

    Inputs with ``competitor_name`` are attached only to that competitor.
    Global inputs are copied to every competitor so downstream analysis remains
    grouped by product instead of creating a fake "research" competitor.
    """
    if not research_inputs:
        return []

    competitor_names = [
        str(c.get("name", "")).strip()
        for c in competitors
        if isinstance(c, dict) and str(c.get("name", "")).strip()
    ]
    by_name = {name.lower(): name for name in competitor_names}
    manual_sources: list[SourceEvidence] = []

    for idx, item in enumerate(research_inputs, start=1):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        source_kind = str(item.get("source_kind", "notes") or "notes").strip()
        title = str(item.get("title", "") or "User research notes").strip()
        requested_name = str(item.get("competitor_name", "") or "").strip()
        target_names = (
            [by_name[requested_name.lower()]]
            if requested_name.lower() in by_name
            else competitor_names
        )

        # User research inputs may contain PII (names, contact info, ID
        # numbers). Mask before persisting so the original is never stored.
        if source_kind in _PII_RESEARCH_KINDS:
            effective_content, contains_pii = sanitize_text(content)
            desensitized = True
        else:
            effective_content = content
            contains_pii = False
            desensitized = False

        for competitor_name in target_names:
            manual_sources.append(
                SourceEvidence(
                    project_id=project_id,
                    competitor_id=_slug(competitor_name),
                    competitor_name=competitor_name,
                    source_type=SourceType.manual_input,
                    url=f"manual://{source_kind}/{idx}",
                    title=title,
                    snippet=effective_content[:300],
                    content=f"Research type: {source_kind}\n\n{effective_content}",
                    retrieved_at=datetime.now(timezone.utc).isoformat(),
                    reliability=Reliability.medium,
                    data_source="manual",
                    contains_pii=contains_pii,
                    desensitized=desensitized,
                )
            )

    return manual_sources


def _collect_live(
    competitor_name: str,
    website: str,
    project_id: str,
    competitor_id: str,
    industry_type: str = "general",
    search_service: SearchService | None = None,
    extra_urls: list[str] | None = None,
    rework_hints: list[str] | None = None,
    custom_dimensions: list[str] | None = None,
) -> _CollectionResult:
    """Crawl a competitor's website using industry-specific paths.

    Returns a ``_CollectionResult`` with full per-competitor stats.
    Fallback semantics (fallback_attempted/used/available) only apply
    in live_with_fallback mode and are recorded here for trace observability.
    """
    competitor_domain = urlparse(website).netloc
    candidate_urls = source_discovery.discover_pages(website, industry_type=industry_type)

    search_urls: list[str] = []
    custom_dimension_urls: list[str] = []
    if search_service is not None:
        try:
            search_urls = search_service.discover_urls(
                competitor_name, website, industry_type, rework_hints=rework_hints,
            )
        except Exception as exc:
            logger.warning(
                "CollectorAgent: SearchService failed for '%s': %s — continuing without search URLs",
                competitor_name,
                exc,
            )
        for hint in _custom_dimension_search_hints(custom_dimensions):
            try:
                found = search_service.discover_urls(
                    competitor_name,
                    website,
                    industry_type,
                    rework_hints=[hint],
                )
                for url in found:
                    if _normalize_url(url) not in {_normalize_url(u) for u in custom_dimension_urls}:
                        custom_dimension_urls.append(url)
            except Exception as exc:
                logger.warning(
                    "CollectorAgent: custom dimension search failed for '%s' (%s): %s",
                    competitor_name,
                    hint,
                    exc,
                )

    # Normalize + filter user-selected URLs (untrusted — same pipeline as M14)
    from app.services.search_service import _normalize_url as _svc_normalize, _is_crawlable
    cleaned_extra: list[str] = []
    rejected_extra: list[dict] = []
    for raw_url in (extra_urls or []):
        norm = _svc_normalize(raw_url)
        if not _is_crawlable(norm):
            rejected_extra.append({"url": raw_url, "reason": "blocked_domain_or_extension"})
        elif norm not in {_svc_normalize(u) for u in cleaned_extra}:
            cleaned_extra.append(raw_url)

    combined_extra = cleaned_extra + search_urls + custom_dimension_urls
    combined_extra_norms = {_normalize_url(u) for u in combined_extra}

    industry_max = get_industry_max_pages(industry_type)
    combined_cap = industry_max + _SEARCH_MAX_URLS
    all_candidates = _deduplicate_urls(candidate_urls + combined_extra)[:combined_cap]

    live_sources: list[SourceEvidence] = []
    failed_urls: list[str] = []
    attempted_norms: set[str] = set()
    attempted_urls: list[str] = []

    if not all_candidates:
        failed_urls.append(website)
    else:
        for url in all_candidates:
            attempted_norms.add(_normalize_url(url))
            attempted_urls.append(url)
            page = crawler_service.crawl_page(url)
            if page is None:
                failed_urls.append(url)
                continue

            source_domain = urlparse(page.url).netloc
            s_type = source_classifier.classify(page.url, page.title, page.content)
            reliability = _assign_reliability(s_type, source_domain, competitor_domain)
            data_source = "search" if _normalize_url(url) in combined_extra_norms else "live"

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
                    data_source=data_source,  # type: ignore[arg-type]
                )
            )

    def crawl_followup_urls(urls: list[str], reason: str) -> None:
        for url in _deduplicate_urls(urls):
            norm = _normalize_url(url)
            if norm in attempted_norms:
                continue
            attempted_norms.add(norm)
            attempted_urls.append(url)
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
                    data_source="search" if reason == "search" else "live",  # type: ignore[arg-type]
                )
            )

    initial_cov = coverage_evaluator.evaluate(live_sources)
    followup_urls: list[str] = []
    known_urls = _KNOWN_FOLLOWUP_URLS.get(competitor_name.strip().lower(), ())
    if not initial_cov.pricing:
        followup_urls.extend([url for url in known_urls if any(part in url.lower() for part in ("pricing", "price", "billing"))])
        if search_service is not None:
            try:
                followup_urls.extend(
                    search_service.discover_urls(
                        competitor_name,
                        website,
                        industry_type,
                        rework_hints=[f"{competitor_name} pricing"],
                    )
                )
            except Exception as exc:
                logger.warning(
                    "CollectorAgent: pricing follow-up search failed for '%s': %s",
                    competitor_name,
                    exc,
                )
    if not initial_cov.features_or_docs:
        followup_urls.extend([url for url in known_urls if any(part in url.lower() for part in ("docs", "documentation", "developers", "code"))])
        if search_service is not None:
            try:
                followup_urls.extend(
                    search_service.discover_urls(
                        competitor_name,
                        website,
                        industry_type,
                        rework_hints=[f"{competitor_name} features docs"],
                    )
                )
            except Exception as exc:
                logger.warning(
                    "CollectorAgent: features follow-up search failed for '%s': %s",
                    competitor_name,
                    exc,
                )
    if followup_urls:
        crawl_followup_urls(followup_urls[: _SEARCH_MAX_URLS * 2], "search")

    cov = coverage_evaluator.evaluate(live_sources)
    fallback_attempted = cov.score < WEAK_THRESHOLD or not all_candidates

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
        attempted_urls=attempted_urls,
        live_source_count=len(live_sources),
        fallback_attempted=fallback_attempted,
        fallback_used=fallback_used,
        fallback_available=fallback_available,
        fallback_source_count=len(fixture_sources),
        selected_extra_urls=cleaned_extra,
        silent_search_urls=search_urls,
        custom_dimension_urls=custom_dimension_urls,
        rejected_extra_urls=rejected_extra,
    )


def run(
    db: Session,
    project_id: str,
    competitors: list[dict],
    goals: list[str],
    rework_hints: list[str] | None = None,
    data_mode: str = "demo",
    industry_type: str = "general",
    research_inputs: list[dict] | None = None,
    custom_dimensions: list[str] | None = None,
    _search_service: SearchService | None = None,
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
        research_inputs: Optional user-supplied survey/interview/questionnaire notes.
        custom_dimensions: Optional user-defined dimensions that should trigger targeted source search.
        _search_service: Optional SearchService for test injection; created
            from config when None and conditions are met.

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
            "custom_dimensions": custom_dimensions or [],
            "research_input_count": len(research_inputs or []),
            "decision_summary": (
                "Collect public source evidence for each competitor; "
                "use QA hints to repair missing evidence when present."
            ),
        },
        status=AgentRunStatus.running,
    )
    trace_service.save_agent_run(db, agent_run)

    try:
        search_svc: SearchService | None = _search_service
        if search_svc is None and data_mode == "live_with_fallback" and settings.enable_live_search:
            provider = create_search_provider(settings.tavily_api_key, enabled=True)
            search_svc = SearchService(provider)

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
                    name, website, project_id, competitor_id, industry_type,
                    search_service=search_svc,
                    extra_urls=comp.get("extra_urls", []) if isinstance(comp, dict) else [],
                    rework_hints=rework_hints or None,
                    custom_dimensions=custom_dimensions or [],
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
                    "selected_extra_url_count": len(result.selected_extra_urls),
                    "silent_search_url_count": len(result.silent_search_urls),
                    "custom_dimension_url_count": len(result.custom_dimension_urls),
                    "selected_extra_urls": result.selected_extra_urls,
                    "silent_search_urls": result.silent_search_urls,
                    "custom_dimension_urls": result.custom_dimension_urls,
                    "rejected_extra_urls": result.rejected_extra_urls,
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

        manual_sources = _build_manual_sources(project_id, competitors, research_inputs)
        if manual_sources:
            all_sources.extend(manual_sources)
            for source in manual_sources:
                stats = collection_stats.setdefault(source.competitor_name, {"source_count": 0})
                stats["source_count"] = int(stats.get("source_count", 0)) + 1
                stats["manual_source_count"] = int(stats.get("manual_source_count", 0)) + 1

        if all_sources:
            source_service.save_sources(db, project_id, all_sources)

        analysis_sources, relevance_by_source_id, relevance_usage, relevance_status = _review_source_relevance(
            all_sources,
            competitors,
            industry_type,
        )

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
                "analysis_source_count": len(analysis_sources),
                "skipped_for_analysis_count": len(all_sources) - len(analysis_sources),
                "manual_source_count": len(manual_sources),
                "failed_urls": all_failed_urls,
                "relevance_review_status": relevance_status,
                "relevance_by_source_id": relevance_by_source_id,
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
                "decision_summary": (
                    f"Collected {len(all_sources)} sources across {len(competitors)} requested competitors."
                ),
                "demo_rework_note": (
                    "Pricing evidence was withheld for the first QA-loop demo pass."
                    if withheld_competitors
                    else ""
                ),
            },
            token_usage=relevance_usage,
            latency_ms=elapsed_ms,
        )
        logger.info(
            "CollectorAgent: collected %d sources for project %s (data_mode=%s, industry=%s)",
            len(all_sources),
            project_id,
            data_mode,
            industry_type,
        )
        return analysis_sources

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
