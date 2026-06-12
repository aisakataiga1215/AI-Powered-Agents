"""AnalystAgent.

Two-stage extraction pipeline:

1. **LLM stage** — The model returns a :class:`RawCompetitorExtraction`
   JSON object. This uses only primitive types (strings, lists of strings)
   so the model does not need to understand Pydantic sub-schemas like
   ``Claim``, ``FeatureCategory``, or ``PricingModel``.

2. **Normalization stage** — :func:`normalization_service.normalize`
   converts the flat extraction to a strict :class:`CompetitorKnowledge`
   deterministically: wrapping strings in ``Claim`` objects, attaching
   source evidence, grouping features by category, etc.

This split means LLM schema-mismatch errors (e.g. ``target_users`` as a
string instead of a list, ``pricing_summary`` as a raw string instead of
a ``Claim`` dict) are caught by the lenient ``RawCompetitorExtraction``
validators or by the normalizer rather than crashing the agent.
"""

import json
import re
import time
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.knowledge import CompetitorKnowledge
from app.schemas.raw_extraction import (
    RawCompetitorExtraction,
    RawFeature,
    RawPricingPlan,
)
from app.schemas.source import SourceEvidence
from app.schemas.trace import AgentRun, AgentRunStatus, TokenUsage
from app.services import normalization_service, trace_service

logger = get_logger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "analyst.md"
_MAX_CONTENT_CHARS = 2000
_RAW_LOG_CHARS = 1000
_TRACE_PREVIEW_CHARS = 1200
_PRICE_RE = re.compile(r"\$\s?\d+(?:\.\d+)?")


def _preview(text: str, limit: int = _TRACE_PREVIEW_CHARS) -> str:
    normalized = " ".join((text or "").split())
    return normalized[:limit] + ("…" if len(normalized) > limit else "")


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _group_sources_by_competitor(
    sources: list[SourceEvidence],
) -> dict[str, list[SourceEvidence]]:
    """Group sources by ``competitor_name`` preserving insertion order."""
    result: dict[str, list[SourceEvidence]] = {}
    for source in sources:
        result.setdefault(source.competitor_name, []).append(source)
    return result


def _build_user_message(
    competitor_name: str,
    sources: list[SourceEvidence],
    goals: list[str],
    analysis_frameworks: list[str] | None = None,
    rework_hints: list[str] | None = None,
    analysis_purpose: str = "unknown",
    competitor_role: str = "direct_competitor",
    custom_dimensions: list[str] | None = None,
) -> str:
    parts: list[str] = []
    for src in sources:
        snippet = src.snippet or ""
        content = (src.content or "")[:_MAX_CONTENT_CHARS]
        parts.append(
            f"[{src.source_id}] {src.title} ({src.source_type.value})\n"
            f"URL: {src.url}\n"
            f"Snippet: {snippet}\n\n"
            f"Content:\n{content}"
        )
    sources_text = "\n\n---\n\n".join(parts) if parts else "(no sources)"

    hints_section = ""
    if rework_hints:
        rendered_hints = "\n".join(f"- {hint}" for hint in rework_hints)
        hints_section = (
            "\n\nPrevious QA feedback to address in this run:\n"
            f"{rendered_hints}\n"
        )

    purpose_section = ""
    if analysis_purpose == "build_product":
        purpose_section = (
            "\n\nAnalysis purpose: BUILD A SIMILAR PRODUCT. Focus on: market gaps this competitor "
            "fails to address, pain points they don't solve, risky product decisions, "
            "and technical approaches worth learning from."
        )
    elif analysis_purpose == "choose_product":
        purpose_section = (
            "\n\nAnalysis purpose: CHOOSE A PRODUCT TO USE. Focus on: strengths and weaknesses "
            "for different user profiles, pricing value, ease of onboarding, maturity, "
            "reliability, and clear differentiators."
        )
    elif analysis_purpose == "understand_industry":
        purpose_section = (
            "\n\nAnalysis purpose: MARKET RESEARCH. Focus on: market segments, major players, "
            "target users, growth drivers, business models, entry barriers, and opportunities."
        )
    elif analysis_purpose == "analyze_growth_ops":
        purpose_section = (
            "\n\nAnalysis purpose: COMPETITOR SUCCESS ANALYSIS. Focus on: positioning, growth path, "
            "core product mechanisms, GTM, monetization, user feedback, and defensible success factors."
        )

    role_section = ""
    if competitor_role == "inspiration_product":
        role_section = (
            f"\n\nCompetitor role: INSPIRATION PRODUCT. "
            "Extract what to learn from this product; it is not a direct competitive threat."
        )
    elif competitor_role == "indirect_competitor":
        role_section = (
            f"\n\nCompetitor role: INDIRECT COMPETITOR. "
            "Note where this product overlaps with and diverges from the core use case."
        )
    elif competitor_role == "benchmark_leader":
        role_section = (
            f"\n\nCompetitor role: BENCHMARK LEADER. "
            "Use this product as the quality and feature bar for comparison."
        )

    dims_section = ""
    if custom_dimensions:
        rendered = ", ".join(custom_dimensions)
        dims_section = (
            f"\n\nAdditional analysis dimensions requested: {rendered}. "
            "Address each explicitly. If evidence is absent, output 'unknown' — do not guess."
        )

    return (
        f"Competitor: {competitor_name}\n"
        f"Goals: {', '.join(goals) if goals else '(none)'}\n"
        f"Frameworks: {', '.join(analysis_frameworks or ['swot'])}\n"
        f"{hints_section}"
        f"{purpose_section}"
        f"{role_section}"
        f"{dims_section}\n"
        f"Sources:\n{sources_text}\n\n"
        "Extract the RawCompetitorExtraction JSON object following the schema "
        "in the system prompt. Use the source_ids shown in square brackets as "
        "reference identifiers — do NOT include them in the JSON output."
    )


def _build_base_llm(*, json_mode: bool) -> ChatOpenAI:
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured; AnalystAgent cannot run."
        )
    kwargs: dict = {
        "model": settings.default_model,
        "api_key": settings.openai_api_key,
        "temperature": 0,
    }
    if json_mode:
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    if settings.llm_disable_thinking:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    return ChatOpenAI(**kwargs)


def _build_json_llm() -> ChatOpenAI:
    return _build_base_llm(json_mode=True)


def _build_function_calling_llm():
    """Build a structured-output LLM that uses native tool/function calling.

    ``include_raw=True`` lets us keep token usage and raw-provider metadata in
    traces while still receiving a Pydantic object as the parsed result.
    """
    return _build_base_llm(json_mode=False).with_structured_output(
        RawCompetitorExtraction,
        method="function_calling",
        include_raw=True,
    )


def _extract_token_usage(response: object) -> TokenUsage:
    meta = getattr(response, "usage_metadata", None)
    if meta and isinstance(meta, dict):
        prompt = int(meta.get("input_tokens", 0))
        completion = int(meta.get("output_tokens", 0))
        total = int(meta.get("total_tokens", 0))
        cost = (
            prompt * settings.openai_input_price_per_1m
            + completion * settings.openai_output_price_per_1m
        ) / 1_000_000
        return TokenUsage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            cost_usd=cost,
        )
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
        return TokenUsage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            cost_usd=cost,
        )
    return TokenUsage()


def _extract_json_text(content: str) -> str:
    """Strip markdown fences the model may emit despite response_format."""
    text = (content or "").strip()
    if text.startswith("```"):
        newline = text.find("\n")
        if newline != -1:
            text = text[newline + 1 :]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
    return text


def _parse_raw_extraction(
    content: str,
    competitor_name: str,
) -> RawCompetitorExtraction | None:
    """Parse LLM JSON into RawCompetitorExtraction. Returns None on failure."""
    raw = _extract_json_text(content)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error(
            "AnalystAgent: JSON parse failed for '%s': %s — raw (truncated): %s",
            competitor_name,
            exc,
            content[:_RAW_LOG_CHARS],
        )
        return None

    # Ensure the LLM didn't omit the name field — backfill before validation.
    if isinstance(data, dict) and not data.get("name"):
        data["name"] = competitor_name

    try:
        return RawCompetitorExtraction.model_validate(data)
    except Exception as exc:  # noqa: BLE001 — Pydantic ValidationError
        logger.error(
            "AnalystAgent: raw schema validation failed for '%s': %s",
            competitor_name,
            exc,
        )
        return None


def _source_type_value(source: SourceEvidence) -> str:
    source_type = getattr(source, "source_type", "")
    return getattr(source_type, "value", str(source_type))


def _first_text(*values: str | None, limit: int = 320) -> str:
    for value in values:
        text = " ".join((value or "").split())
        if text:
            return text[:limit]
    return ""


def _source_fallback_extraction(
    competitor_name: str,
    sources: list[SourceEvidence],
) -> RawCompetitorExtraction | None:
    """Build minimal useful extraction from collected sources when LLM is empty."""
    if not sources:
        return None

    official_sources = [
        source for source in sources
        if _source_type_value(source) in {"official_website", "docs", "features_page"}
    ]
    pricing_sources = [
        source for source in sources
        if _source_type_value(source) == "pricing_page"
    ]
    feedback_sources = [
        source for source in sources
        if _source_type_value(source) == "review"
        or getattr(source, "data_source", None) == "manual"
    ]

    primary = (official_sources or sources)[0]
    positioning = _first_text(primary.snippet, primary.content, primary.title)

    feature_items: list[RawFeature] = []
    seen_features: set[str] = set()
    for source in official_sources or sources:
        title = _first_text(source.title, source.snippet, limit=90)
        if not title:
            continue
        normalized_title = title.lower()
        if normalized_title in seen_features:
            continue
        seen_features.add(normalized_title)
        feature_items.append(
            RawFeature(
                name=title,
                category="Product",
                availability="available",
                description=_first_text(source.snippet, source.content, limit=220),
            )
        )
        if len(feature_items) >= 6:
            break

    pricing_summary = ""
    pricing_url = ""
    pricing_plans: list[RawPricingPlan] = []
    has_free_plan = False
    if pricing_sources:
        pricing_source = pricing_sources[0]
        pricing_url = pricing_source.url
        pricing_summary = _first_text(
            pricing_source.snippet,
            pricing_source.content,
            pricing_source.title,
        )
        pricing_text = f"{pricing_summary} {pricing_source.title}".lower()
        has_free_plan = "free" in pricing_text or "免费" in pricing_text
        pricing_plans = _extract_fallback_pricing_plans(
            f"{pricing_source.title} {pricing_source.snippet} {pricing_source.content}"
        )
        if not pricing_plans:
            pricing_plans.append(
                RawPricingPlan(
                    name="Pricing information",
                    price="See pricing page",
                    billing_cycle="unknown",
                    features=[pricing_summary] if pricing_summary else [],
                )
            )

    feedback_summary = ""
    positive_points: list[str] = []
    negative_points: list[str] = []
    if feedback_sources:
        feedback_summary = _first_text(
            feedback_sources[0].snippet,
            feedback_sources[0].content,
            feedback_sources[0].title,
        )
        if feedback_summary:
            positive_points.append(feedback_summary)

    target_users: list[str] = []
    combined = " ".join(
        _first_text(source.title, source.snippet, source.content, limit=200).lower()
        for source in sources[:5]
    )
    if any(term in combined for term in ["developer", "code", "coding", "ide", "工程师", "开发"]):
        target_users.append("Developers and engineering teams")
    elif any(term in combined for term in ["marketer", "growth", "sales", "运营", "增长"]):
        target_users.append("Growth, marketing, and operations teams")
    elif positioning:
        target_users.append(f"Users evaluating {competitor_name}")

    weakness = ""
    if pricing_summary:
        weakness = (
            "Pricing and package fit need manual verification against the "
            "pricing source before purchase or benchmark decisions."
        )
    elif positioning:
        weakness = (
            "Public evidence is concentrated in official positioning pages, "
            "so limitations and trade-offs require additional validation."
        )

    opportunity = ""
    if target_users and feature_items:
        opportunity = (
            f"{target_users[0]} can be served through the product capabilities "
            f"visible in collected sources, including {feature_items[0].name}."
        )
    elif positioning:
        opportunity = (
            "The positioning evidence suggests adjacent use cases that can be "
            "benchmarked for product and go-to-market planning."
        )

    threat = ""
    if feature_items or pricing_summary:
        threat = (
            "Comparable products can compete on overlapping features, pricing, "
            "and onboarding unless differentiation is validated with user evidence."
        )
    elif positioning:
        threat = (
            "The publicly visible positioning may be easy for competitors to copy "
            "without stronger evidence of defensibility."
        )

    raw = RawCompetitorExtraction(
        name=competitor_name,
        website=primary.url,
        company=competitor_name,
        positioning=positioning,
        target_users=target_users,
        features=feature_items,
        has_free_plan=has_free_plan,
        pricing_url=pricing_url,
        pricing_plans=pricing_plans,
        pricing_summary=pricing_summary,
        positive_points=positive_points,
        negative_points=negative_points,
        user_feedback_summary=feedback_summary,
        strengths=[positioning] if positioning else [],
        weaknesses=[weakness] if weakness else [],
        opportunities=[opportunity] if opportunity else [],
        threats=[threat] if threat else [],
    )

    if (
        raw.positioning
        or raw.features
        or raw.pricing_summary
        or raw.pricing_plans
        or raw.target_users
    ):
        return raw
    return None


def _extract_fallback_pricing_plans(text: str) -> list[RawPricingPlan]:
    normalized = " ".join((text or "").split())
    if not normalized:
        return []

    plans: list[RawPricingPlan] = []
    lowered = normalized.lower()
    if "free" in lowered or "免费" in lowered:
        plans.append(
            RawPricingPlan(
                name="Free",
                price="free",
                billing_cycle="monthly",
                features=[],
            )
        )

    seen_prices: set[str] = set()
    for match in _PRICE_RE.finditer(normalized):
        price = match.group(0).replace(" ", "")
        if price in seen_prices:
            continue
        seen_prices.add(price)
        start = max(0, match.start() - 40)
        end = min(len(normalized), match.end() + 80)
        context = normalized[start:end]
        cycle_text = context.lower()
        billing_cycle = "yearly" if any(term in cycle_text for term in ["year", "annual", "yearly", "年"]) else "monthly"
        name = "Paid plan"
        before = normalized[start:match.start()].strip(" ,;:|-/")
        words = [word.strip(" ,;:|-/") for word in before.split() if word.strip(" ,;:|-/")]
        if words:
            candidate = words[-1]
            if candidate.lower() not in {"pricing", "plan", "plus", "includes"}:
                name = candidate[:40]
        plans.append(
            RawPricingPlan(
                name=name,
                price=price,
                billing_cycle=billing_cycle,
                features=[context[:180]],
            )
        )
        if len(plans) >= 5:
            break
    return plans


def _has_actionable_extraction(raw: RawCompetitorExtraction) -> bool:
    return bool(
        raw.positioning
        or raw.target_users
        or raw.features
        or raw.pricing_summary
        or raw.pricing_plans
        or raw.user_feedback_summary
        or raw.strengths
        or raw.weaknesses
    )


def run(
    db: Session,
    project_id: str,
    sources: list[SourceEvidence],
    goals: list[str],
    analysis_frameworks: list[str] | None = None,
    rework_hints: list[str] | None = None,
    analysis_purpose: str = "unknown",
    custom_dimensions: list[str] | None = None,
    competitor_roles: dict[str, str] | None = None,
) -> list[CompetitorKnowledge]:
    """Extract structured knowledge for each competitor from sources.

    Args:
        db: SQLAlchemy session.
        project_id: Owning project id.
        sources: All source evidence collected by the collector.
        goals: Analysis goals (e.g. ``["pricing_analysis"]``).
        analysis_frameworks: Analysis frameworks requested for the report.
        rework_hints: Optional QA hints from a previous failed run.
        analysis_purpose: Decision-support purpose string.
        custom_dimensions: Optional user-defined analysis dimensions.
        competitor_roles: Mapping of competitor name to role string.

    Returns:
        One :class:`CompetitorKnowledge` per distinct competitor.
    """
    run_id = f"run_{__import__('uuid').uuid4().hex[:8]}"
    start = time.time()

    agent_run = AgentRun(
        agent_run_id=run_id,
        project_id=project_id,
        agent_name="AnalystAgent",
        input={
            "source_count": len(sources),
            "goals": goals,
            "analysis_frameworks": analysis_frameworks or ["swot"],
            "rework_hints": rework_hints or [],
            "analysis_purpose": analysis_purpose,
            "custom_dimensions": custom_dimensions or [],
            "decision_summary": "Extract normalized competitor knowledge from collected evidence.",
        },
        status=AgentRunStatus.running,
    )
    trace_service.save_agent_run(db, agent_run)

    try:
        system_prompt = _load_prompt()
        function_llm = _build_function_calling_llm()
        json_llm: ChatOpenAI | None = None

        grouped = _group_sources_by_competitor(sources)
        if not grouped:
            raise ValueError(
                "AnalystAgent received no sources; collector must run first."
            )

        results: list[CompetitorKnowledge] = []
        total_usage = TokenUsage()
        prompt_previews: dict[str, str] = {}
        llm_output_previews: dict[str, str] = {}
        parse_status_by_competitor: dict[str, str] = {}
        empty_extraction_count = 0

        for competitor_name, comp_sources in grouped.items():
            user_message = _build_user_message(
                competitor_name=competitor_name,
                sources=comp_sources,
                goals=goals,
                analysis_frameworks=analysis_frameworks,
                rework_hints=rework_hints,
                analysis_purpose=analysis_purpose,
                competitor_role=(competitor_roles or {}).get(competitor_name, "direct_competitor"),
                custom_dimensions=custom_dimensions,
            )
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message),
            ]
            source_ids = [s.source_id for s in comp_sources]
            prompt_previews[competitor_name] = _preview(user_message)

            raw_extraction: RawCompetitorExtraction | None = None
            try:
                structured_response = function_llm.invoke(messages)
                raw_message = structured_response.get("raw") if isinstance(structured_response, dict) else None
                parsed = structured_response.get("parsed") if isinstance(structured_response, dict) else structured_response
                parsing_error = structured_response.get("parsing_error") if isinstance(structured_response, dict) else None
                if parsing_error is not None:
                    raise ValueError(f"function calling parse error: {parsing_error}")
                if isinstance(parsed, RawCompetitorExtraction):
                    raw_extraction = parsed
                else:
                    raw_extraction = RawCompetitorExtraction.model_validate(parsed)
                if not raw_extraction.name:
                    raw_extraction.name = competitor_name
                llm_output_previews[competitor_name] = _preview(
                    json.dumps(raw_extraction.model_dump(mode="json"), ensure_ascii=False)
                )
                parse_status_by_competitor[competitor_name] = "function_calling_parsed"
                usage = _extract_token_usage(raw_message)
                total_usage = TokenUsage(
                    prompt_tokens=total_usage.prompt_tokens + usage.prompt_tokens,
                    completion_tokens=total_usage.completion_tokens + usage.completion_tokens,
                    total_tokens=total_usage.total_tokens + usage.total_tokens,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "AnalystAgent: function calling failed for '%s': %s; falling back to JSON output.",
                    competitor_name,
                    exc,
                )
                try:
                    if json_llm is None:
                        json_llm = _build_json_llm()
                    response = json_llm.invoke(messages)
                    content = getattr(response, "content", "") or ""
                    llm_output_previews[competitor_name] = _preview(str(content))
                    raw_extraction = _parse_raw_extraction(content, competitor_name)
                    parse_status_by_competitor[competitor_name] = (
                        "json_output_parsed" if raw_extraction is not None else "json_output_fallback_empty"
                    )
                    usage = _extract_token_usage(response)
                    total_usage = TokenUsage(
                        prompt_tokens=total_usage.prompt_tokens + usage.prompt_tokens,
                        completion_tokens=total_usage.completion_tokens + usage.completion_tokens,
                        total_tokens=total_usage.total_tokens + usage.total_tokens,
                    )
                except Exception as json_exc:  # noqa: BLE001
                    parse_status_by_competitor[competitor_name] = "llm_error_fallback_empty"
                    logger.error(
                        "AnalystAgent: JSON fallback failed for '%s': %s; using empty knowledge.",
                        competitor_name,
                        json_exc,
                    )

            if raw_extraction is None:
                fallback_extraction = _source_fallback_extraction(
                    competitor_name,
                    comp_sources,
                )
                if fallback_extraction is not None:
                    raw_extraction = fallback_extraction
                    parse_status_by_competitor[competitor_name] = (
                        f"{parse_status_by_competitor.get(competitor_name, 'llm_error')}_source_fallback"
                    )
                    llm_output_previews[competitor_name] = _preview(
                        json.dumps(raw_extraction.model_dump(mode="json"), ensure_ascii=False)
                    )
                else:
                    logger.error(
                        "AnalystAgent: raw extraction failed for '%s'; no usable source fallback.",
                        competitor_name,
                    )
                    raw_extraction = RawCompetitorExtraction(name=competitor_name)

            if not _has_actionable_extraction(raw_extraction):
                empty_extraction_count += 1

            knowledge = normalization_service.normalize(
                raw_extraction,
                source_ids=source_ids,
                sources=comp_sources,
            )
            results.append(knowledge)

        elapsed_ms = int((time.time() - start) * 1000)
        all_extractions_empty = empty_extraction_count == len(results)
        trace_service.update_agent_run(
            db,
            run_id,
            status=(
                AgentRunStatus.failed
                if all_extractions_empty
                else AgentRunStatus.success
            ),
            error_message=(
                "AnalystAgent could not extract actionable knowledge from LLM output or source fallback."
                if all_extractions_empty
                else None
            ),
            output={
                "knowledge_count": len(results),
                "competitors": [k.competitor_name for k in results],
                "empty_extraction_count": empty_extraction_count,
                "decision_summary": (
                    "AnalystAgent could not extract actionable knowledge from any competitor."
                    if all_extractions_empty
                    else f"Generated structured knowledge for {len(results)} competitors."
                ),
                "prompt_preview": prompt_previews,
                "llm_output_preview": llm_output_previews,
                "parse_status": parse_status_by_competitor,
            },
            latency_ms=elapsed_ms,
            token_usage=total_usage,
        )
        logger.info(
            "AnalystAgent: analyzed %d competitors for project %s",
            len(results),
            project_id,
        )
        return results

    except Exception as exc:
        elapsed_ms = int((time.time() - start) * 1000)
        trace_service.update_agent_run(
            db,
            run_id,
            status=AgentRunStatus.failed,
            error_message=str(exc),
            latency_ms=elapsed_ms,
        )
        logger.error("AnalystAgent failed: %s", exc)
        raise
