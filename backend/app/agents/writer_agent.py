"""WriterAgent.

Synthesizes a :class:`CompetitiveReport` from structured competitor
knowledge using an LLM in **JSON Output mode**.

Why JSON output instead of ``with_structured_output``:
DeepSeek's OpenAI-compatible endpoint reliably returns plain assistant
content for this task and frequently refuses the tool-call path that
LangChain's ``with_structured_output(method="function_calling")``
expects, leaving the workflow stuck on a ``None`` return. JSON output
mode (``response_format={"type": "json_object"}``) is the supported way
to get strict-JSON responses from DeepSeek; we then parse, normalize,
and validate against :class:`CompetitiveReport` ourselves.

The writer never raises on LLM/parsing/validation failure — it always
produces a valid (possibly minimal) :class:`CompetitiveReport` so the
QA agent can flag the gap and decide on rework instead of the workflow
dying mid-graph.
"""

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.knowledge import CompetitorKnowledge
from app.schemas.pm_sections import FeatureInsights, MarketBackground, OperationMonetization
from app.schemas.report import CompetitiveReport
from app.schemas.scoring import CompetitorScore, OpportunityScore
from app.schemas.source import SourceEvidence
from app.schemas.trace import AgentRun, AgentRunStatus, TokenUsage
from app.services import trace_service
from app.services.markdown_renderer import render_report_markdown
from app.services.normalization_service import normalize_feature_category

logger = get_logger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "writer.md"
_MAX_KNOWLEDGE_CHARS = 3000
_RAW_RESPONSE_LOG_CHARS = 2000


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _serialize_knowledge(knowledge: list[CompetitorKnowledge]) -> str:
    """Compact JSON dump of competitor knowledge, capped per competitor."""
    rendered: list[str] = []
    for ck in knowledge:
        payload = ck.model_dump(mode="json")
        text = json.dumps(payload, ensure_ascii=False)
        if len(text) > _MAX_KNOWLEDGE_CHARS:
            text = text[:_MAX_KNOWLEDGE_CHARS] + " ...(truncated)"
        rendered.append(text)
    return "\n\n".join(rendered)


def _render_source_index(sources: list[SourceEvidence]) -> str:
    """Render a compact index of available source ids for the prompt."""
    if not sources:
        return "(no sources available)"
    lines = [
        f"- {s.source_id} | {s.competitor_name} | {s.source_type.value} | {s.title}"
        for s in sources
    ]
    return "\n".join(lines)


def _build_user_message(
    competitor_knowledge: list[CompetitorKnowledge],
    sources: list[SourceEvidence],
    goals: list[str],
    rework_hints: list[str] | None,
    output_language: str = "en",
    analysis_purpose: str = "general",
    custom_dimensions: list[str] | None = None,
) -> str:
    hints_section = ""
    if rework_hints:
        rendered_hints = "\n".join(f"- {hint}" for hint in rework_hints)
        hints_section = (
            "\n\nPrevious QA feedback to address in this run:\n"
            f"{rendered_hints}\n"
        )

    lang_instruction = ""
    if output_language == "zh":
        lang_instruction = (
            "\n\nREMINDER — write all user-facing text in Simplified Chinese (简体中文).\n"
        )

    purpose_instruction = (
        "\n\nOutput these fields in addition to existing ones:\n"
        f'"analysis_purpose": "{analysis_purpose}",\n'
        '"analysis_objective": "one-sentence statement of what this analysis accomplishes",\n'
        '"competitor_selection_rationale": {<comp_name>: "why included based on its role"},\n'
    )

    if analysis_purpose == "choose_product":
        purpose_instruction += (
            '\n"competitor_scores": {\n'
            '  <comp_name>: {\n'
            '    "competitor_name": <comp_name>,\n'
            '    "overall_score": <float 0-100>,\n'
            '    "dimensions": [{"dimension_name": str, "score": int 1-5, "rationale": str, "evidence": [src_ids], "source_confidence": "high"|"medium"|"low"|"unknown"}],\n'
            '    "scoring_note": "Scores are model-assisted evaluations, not objective measurements."\n'
            '  }\n'
            '}\n'
            'Scoring dimensions: feature_fit, pricing_value, ease_of_use, maturity, privacy_security, source_confidence_overall.\n'
            '\n"purpose_sections": {\n'
            '  "recommendation_ranking": [{"rank": int, "competitor_name": str, "summary": str}],\n'
            '  "best_for": {<comp_name>: "use case description"},\n'
            '  "who_should_avoid": {<comp_name>: "reason"},\n'
            '  "decision_matrix": [{"criterion": str, <comp_name>: {"value": str, "evidence": [src_ids]}}]\n'
            '}\n'
        )
    elif analysis_purpose == "build_product":
        purpose_instruction += (
            '\n"opportunity_score": {\n'
            '  "overall_score": <float 0-100>,\n'
            '  "dimensions": [{"dimension_name": str, "score": int 1-5, "rationale": str, "evidence": [src_ids], "source_confidence": "high"|"medium"|"low"|"unknown"}],\n'
            '  "scoring_note": "Scores are model-assisted evaluations, not objective measurements."\n'
            '}\n'
            'Opportunity dimensions: market_gap, pain_intensity, differentiation_potential, feasibility, monetization_potential, competitive_risk.\n'
            '\n"purpose_sections": {\n'
            '  "features_to_learn_from": [{"competitor_name": str, "feature": str, "rationale": str, "evidence": [src_ids]}],\n'
            '  "pitfalls_to_avoid": [{"competitor_name": str, "pitfall": str, "risk_level": "high"|"medium"|"low", "evidence": [src_ids]}],\n'
            '  "market_gaps": [{"gap_description": str, "evidence": [src_ids], "affected_user_segment": str}],\n'
            '  "mvp_direction": "prose recommendation",\n'
            '  "differentiation_opportunities": [{"opportunity": str, "rationale": str}]\n'
            '}\n'
        )

    dims_instruction = ""
    if custom_dimensions:
        rendered = ", ".join(f'"{d}"' for d in custom_dimensions)
        dims_instruction = (
            f'\n"custom_dimension_analysis": {{\n'
            f'  <dim_name for each of {rendered}>: {{\n'
            f'    <comp_name>: {{"score": 1-5 or "unknown", "rationale": str, "evidence": [src_ids], "source_confidence": "high"|"medium"|"low"|"unknown"}}\n'
            f'  }}\n'
            f'}}\n'
            "If no evidence is found for a dimension, use \"unknown\" for score — do not guess.\n"
        )

    return (
        f"Report goals: {', '.join(goals) if goals else '(none)'}\n"
        f"{hints_section}\n"
        f"Available source ids (use these in claim evidence):\n"
        f"{_render_source_index(sources)}\n\n"
        f"Competitor knowledge (JSON, one per competitor):\n"
        f"{_serialize_knowledge(competitor_knowledge)}\n\n"
        f"{lang_instruction}"
        f"{purpose_instruction}"
        f"{dims_instruction}"
        f"{_PM_SECTIONS_INSTRUCTION}"
        "Return ONE JSON object matching the CompetitiveReport schema. "
        "Every executive_summary and strategic_recommendations entry MUST "
        "be an object with 'text', 'evidence' (list of source_ids), and "
        "'is_hypothesis'. Do not invent sources. Do not wrap the response "
        "in markdown fences."
    )


_PM_SECTIONS_INSTRUCTION = """
Output these three PM-framework sections in addition to existing fields:

"market_background": {
  "market_overview": "2-3 sentence overview of the competitive landscape and market dynamics",
  "market_size_notes": "any TAM/SAM estimates found in sources, or qualitative market size description",
  "trends": [{"trend": "trend description", "evidence": ["src_xxx"]}],
  "key_drivers": ["growth driver 1", "growth driver 2"],
  "key_challenges": ["market challenge 1"]
}

"feature_insights": {
  "table_stakes": ["feature all or most competitors offer"],
  "differentiators": [{"feature": "feature name", "competitors": ["CompetitorA"]}],
  "gaps": ["feature category no competitor addresses — potential market opportunity"],
  "cross_competitor_patterns": ["cross-cutting pattern or trend observed across competitors"]
}

"operation_monetization": {
  "gtm_profiles": [{
    "competitor_name": "name",
    "motion": "PLG|sales_led|marketing_led|channel|hybrid",
    "acquisition_channels": ["organic search", "product-led trial"],
    "pricing_strategy": "freemium|per_seat|usage_based|flat_rate|enterprise",
    "expansion_model": "how they expand revenue from existing customers",
    "evidence": ["src_xxx"]
  }],
  "monetization_patterns": ["cross-competitor monetization observation"],
  "aarrr_notes": {
    "acquisition": {"CompetitorA": "how they acquire users"},
    "activation": {"CompetitorA": "onboarding / first value approach"},
    "retention": {"CompetitorA": "stickiness and retention mechanics"},
    "referral": {"CompetitorA": "referral / virality / word-of-mouth"},
    "revenue": {"CompetitorA": "revenue model and expansion levers"}
  }
}

Use only evidence from provided sources. If a field cannot be determined, omit it or use an empty array — do not guess.
"""


def _build_json_llm() -> ChatOpenAI:
    """Construct a ChatOpenAI client bound to JSON-object response mode."""
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured; WriterAgent cannot run."
        )
    kwargs: dict = {
        "model": settings.default_model,
        "api_key": settings.openai_api_key,
        "temperature": 0,
        # ``response_format`` is an OpenAI request param; ``model_kwargs``
        # is the langchain-openai escape hatch for forwarding it.
        "model_kwargs": {"response_format": {"type": "json_object"}},
    }
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    if settings.llm_disable_thinking:
        # ``extra_body`` is a first-class ChatOpenAI field; passing the
        # thinking-disable flag through ``model_kwargs`` would have the
        # OpenAI client reject it as an unknown argument.
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    return ChatOpenAI(**kwargs)


def _extract_token_usage(response: Any) -> TokenUsage:
    """Extract token counts from a LangChain AIMessage response.

    LangChain stores usage in response.usage_metadata (preferred) or
    response.response_metadata["token_usage"]. Returns a zero TokenUsage
    if the provider does not return usage data.
    """
    # Preferred: LangChain's unified usage_metadata (dict with input_tokens, etc.)
    meta = getattr(response, "usage_metadata", None)
    if meta and isinstance(meta, dict):
        return TokenUsage(
            prompt_tokens=int(meta.get("input_tokens", 0)),
            completion_tokens=int(meta.get("output_tokens", 0)),
            total_tokens=int(meta.get("total_tokens", 0)),
        )
    # Fallback: raw response_metadata from OpenAI-compatible providers
    resp_meta = getattr(response, "response_metadata", None) or {}
    usage = resp_meta.get("token_usage") or resp_meta.get("usage") or {}
    if usage:
        return TokenUsage(
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            total_tokens=int(usage.get("total_tokens", 0)),
        )
    return TokenUsage()


def _extract_json_text(content: str) -> str:
    """Strip ``` fences/preface text that the model may emit despite
    response_format. Returns the first ``{...}`` block if a brace pair
    can be located, otherwise the stripped content.
    """
    text = (content or "").strip()
    if text.startswith("```"):
        # Drop opening ``` or ```json line
        newline = text.find("\n")
        if newline != -1:
            text = text[newline + 1 :]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    # Last-resort: carve out the outermost JSON object.
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
    return text


def _to_claim_dict_list(value: Any) -> list[dict]:
    """Coerce model-emitted claim arrays into Claim-compatible dicts.

    DeepSeek sometimes returns claims as bare strings or wraps a single
    claim as one string. Pydantic ``list[Claim]`` validation then aborts
    the whole report. Normalising to ``{"text": ..., "evidence": [],
    "is_hypothesis": True}`` keeps the report intact and lets QA flag
    the missing evidence.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [{"text": value, "evidence": [], "is_hypothesis": True}]
    if isinstance(value, dict):
        return [value]
    if not isinstance(value, list):
        return []
    result: list[dict] = []
    for item in value:
        if isinstance(item, dict):
            result.append(item)
        elif isinstance(item, str) and item.strip():
            result.append(
                {"text": item, "evidence": [], "is_hypothesis": True}
            )
    return result


def _to_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _normalize_report_payload(data: Any) -> dict:
    """Ensure the parsed JSON has the shapes ``CompetitiveReport`` expects."""
    if not isinstance(data, dict):
        return {}
    data["executive_summary"] = _to_claim_dict_list(
        data.get("executive_summary")
    )
    data["strategic_recommendations"] = _to_claim_dict_list(
        data.get("strategic_recommendations")
    )
    for key in (
        "feature_comparison",
        "pricing_comparison",
        "user_persona_comparison",
        "swot_comparison",
    ):
        data[key] = _to_dict(data.get(key))
    if not isinstance(data.get("markdown_content"), str):
        data["markdown_content"] = ""

    # New purpose-analysis fields — all default gracefully on absent/invalid data.
    if not isinstance(data.get("analysis_purpose"), str):
        data["analysis_purpose"] = "general"
    if not isinstance(data.get("analysis_objective"), str):
        data["analysis_objective"] = ""
    if not isinstance(data.get("competitor_selection_rationale"), dict):
        data["competitor_selection_rationale"] = {}
    if not isinstance(data.get("purpose_sections"), dict):
        data["purpose_sections"] = {}
    if not isinstance(data.get("custom_dimension_analysis"), dict):
        data["custom_dimension_analysis"] = {}

    # Validate competitor_scores: keep valid entries, drop invalid ones.
    raw_scores = data.get("competitor_scores")
    validated_scores: dict = {}
    if isinstance(raw_scores, dict):
        for name, val in raw_scores.items():
            try:
                validated_scores[name] = CompetitorScore.model_validate(val).model_dump(mode="json")
            except Exception:  # noqa: BLE001
                pass
    data["competitor_scores"] = validated_scores

    # Validate opportunity_score: None on any failure.
    raw_opp = data.get("opportunity_score")
    if raw_opp is not None:
        try:
            data["opportunity_score"] = OpportunityScore.model_validate(raw_opp).model_dump(mode="json")
        except Exception:  # noqa: BLE001
            data["opportunity_score"] = None

    # M13B: PM-framework sections — validate each, default to None on failure.
    try:
        mb = data.get("market_background")
        data["market_background"] = MarketBackground.model_validate(mb).model_dump(mode="json") if mb else None
    except Exception:  # noqa: BLE001
        data["market_background"] = None

    try:
        fi = data.get("feature_insights")
        data["feature_insights"] = FeatureInsights.model_validate(fi).model_dump(mode="json") if fi else None
    except Exception:  # noqa: BLE001
        data["feature_insights"] = None

    try:
        om = data.get("operation_monetization")
        data["operation_monetization"] = OperationMonetization.model_validate(om).model_dump(mode="json") if om else None
    except Exception:  # noqa: BLE001
        data["operation_monetization"] = None

    return data


def _build_fallback_report(
    project_id: str,
    competitor_knowledge: list[CompetitorKnowledge],
    sources: list[SourceEvidence],
    goals: list[str],
    reason: str,
) -> CompetitiveReport:
    """Construct a minimal but valid CompetitiveReport when the LLM path
    fails. QA will see the empty executive_summary / recommendations and
    can route a targeted rework to the writer.
    """
    competitor_names = [
        ck.competitor_name for ck in competitor_knowledge if ck.competitor_name
    ]
    title = (
        f"Competitive Analysis Report: {', '.join(competitor_names)}"
        if competitor_names
        else "Competitive Analysis Report"
    )
    lines = [
        f"# {title}",
        "",
        "_This report was generated as a fallback because the writer "
        f"could not produce a structured response. Reason: {reason}._",
        "",
        "## Competitors covered",
    ]
    for ck in competitor_knowledge:
        lines.append(f"- {ck.competitor_name or '(unnamed)'}")
    if goals:
        lines.extend(["", "## Goals", *(f"- {goal}" for goal in goals)])
    return CompetitiveReport(
        project_id=project_id,
        title=title,
        executive_summary=[],
        competitor_overview=list(competitor_knowledge),
        feature_comparison={},
        pricing_comparison={},
        user_persona_comparison={},
        swot_comparison={},
        strategic_recommendations=[],
        source_list=list(sources),
        markdown_content="\n".join(lines),
    )


def _produce_report(
    llm: ChatOpenAI,
    messages: list,
    project_id: str,
    competitor_knowledge: list[CompetitorKnowledge],
    sources: list[SourceEvidence],
    goals: list[str],
) -> tuple[CompetitiveReport, bool, TokenUsage]:
    """Invoke the LLM, parse JSON, validate, fall back on any failure.

    Returns ``(report, is_fallback, token_usage)`` so the caller can record
    the distinction in the trace record without raising. ``token_usage`` is
    a zero :class:`TokenUsage` on any error/fallback path.
    """
    try:
        response = llm.invoke(messages)
    except Exception as exc:  # noqa: BLE001 — log + fallback by design
        logger.error(
            "WriterAgent: LLM invocation failed: %s; using fallback report.",
            exc,
        )
        return (
            _build_fallback_report(
                project_id,
                competitor_knowledge,
                sources,
                goals,
                f"LLM invocation error: {exc}",
            ),
            True,
            TokenUsage(),
        )

    token_usage = _extract_token_usage(response)

    content = getattr(response, "content", "") or ""
    if not isinstance(content, str):
        # Some providers return content as a list of content blocks; join.
        content = "".join(
            getattr(block, "text", "") if hasattr(block, "text") else str(block)
            for block in content
        )

    if not content.strip():
        logger.error(
            "WriterAgent: LLM returned empty content; using fallback report."
        )
        return (
            _build_fallback_report(
                project_id,
                competitor_knowledge,
                sources,
                goals,
                "empty LLM response",
            ),
            True,
            TokenUsage(),
        )

    raw_text = _extract_json_text(content)
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error(
            "WriterAgent: JSON parse failed: %s; raw response (truncated): %s",
            exc,
            content[:_RAW_RESPONSE_LOG_CHARS],
        )
        return (
            _build_fallback_report(
                project_id,
                competitor_knowledge,
                sources,
                goals,
                f"JSON parse error: {exc}",
            ),
            True,
            TokenUsage(),
        )

    data = _normalize_report_payload(data)

    try:
        report = CompetitiveReport.model_validate(data)
    except Exception as exc:  # noqa: BLE001 — Pydantic raises ValidationError
        logger.error(
            "WriterAgent: schema validation failed: %s; raw response "
            "(truncated): %s",
            exc,
            content[:_RAW_RESPONSE_LOG_CHARS],
        )
        return (
            _build_fallback_report(
                project_id,
                competitor_knowledge,
                sources,
                goals,
                f"schema validation error: {exc}",
            ),
            True,
            TokenUsage(),
        )

    return report, False, token_usage


def _build_feature_comparison(
    knowledge: list[CompetitorKnowledge],
) -> dict[str, str]:
    """Build feature_comparison deterministically from structured feature_tree.

    Produces a dict mapping competitor_name -> compact feature summary string,
    grouped by canonical category. Categories that differ in raw form but share
    the same canonical name (e.g. "AI Agent" + "Agent Management" → "AI Agents")
    are merged into a single row to prevent duplicate table entries.
    """
    result: dict[str, str] = {}
    for ck in knowledge:
        if not ck.feature_tree:
            continue
        # Accumulate features per canonical category before building the string
        merged: dict[str, list[str]] = {}
        for cat in ck.feature_tree:
            canonical = normalize_feature_category(cat.category)
            feature_names = [
                f.name
                for f in cat.features
                if f.availability != "unknown" and f.name
            ]
            if canonical in merged:
                merged[canonical].extend(feature_names)
            else:
                merged[canonical] = feature_names
        cat_parts = [
            f"{canonical}: {', '.join(names)}"
            for canonical, names in merged.items()
            if names
        ]
        if cat_parts:
            result[ck.competitor_name] = " | ".join(cat_parts)
    return result


def _build_pricing_comparison(
    knowledge: list[CompetitorKnowledge],
) -> dict[str, str]:
    """Build pricing_comparison deterministically from structured pricing_model.plans.

    Produces a dict mapping competitor_name -> compact pricing summary string.
    Uses exact plan name, price, and billing_cycle from structured data;
    never calls the LLM for this.
    """
    result: dict[str, str] = {}
    for ck in knowledge:
        if not ck.pricing_model or not ck.pricing_model.plans:
            continue
        parts: list[str] = []
        for plan in ck.pricing_model.plans:
            price_str = (
                plan.price.strip()
                if plan.price.strip().lower() == "free"
                else f"{plan.price.strip()}/{plan.billing_cycle.strip()}"
            )
            parts.append(f"{plan.name}: {price_str}")
        if parts:
            result[ck.competitor_name] = " | ".join(parts)
    return result


def _build_pricing_markdown(
    knowledge: list[CompetitorKnowledge],
    output_language: str = "en",
) -> str:
    """Build a markdown pricing table deterministically from pricing_model.plans."""
    rows: list[tuple[str, str, str, str]] = []
    for ck in knowledge:
        if not ck.pricing_model or not ck.pricing_model.plans:
            continue
        for plan in ck.pricing_model.plans:
            rows.append((
                ck.competitor_name,
                plan.name,
                plan.price,
                plan.billing_cycle,
            ))
    if not rows:
        return ""
    if output_language == "zh":
        header = "| 竞品 | 方案 | 价格 | 计费周期 |\n|---|---|---|---|"
        section_heading = "## 定价对比"
    else:
        header = "| Competitor | Plan | Price | Billing |\n|---|---|---|---|"
        section_heading = "## Pricing Comparison"
    data_lines = [
        f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |"
        for r in rows
    ]
    return section_heading + "\n\n" + header + "\n" + "\n".join(data_lines)


def _bind_report_fields(
    report: CompetitiveReport,
    project_id: str,
    competitor_knowledge: list[CompetitorKnowledge],
    sources: list[SourceEvidence],
    output_language: str = "en",
) -> CompetitiveReport:
    """Backfill fields the LLM commonly omits or fills incorrectly."""
    report.project_id = project_id
    # Always use the analyst's structured knowledge as the authoritative
    # competitor_overview so QA's pricing_consistency check compares the same
    # data source that _build_pricing_comparison uses.
    report.competitor_overview = list(competitor_knowledge)
    # Always overwrite source_list with the real evidence objects.
    report.source_list = list(sources)

    # Overwrite pricing_comparison with deterministic values from structured data.
    # This prevents the LLM from inventing or mis-summarising prices.
    det_pricing = _build_pricing_comparison(competitor_knowledge)
    if det_pricing:
        report.pricing_comparison = det_pricing

    # Overwrite feature_comparison with deterministic values from feature_tree.
    # Prevents the LLM from contradicting the analyst's structured availability data
    # (e.g. marking a feature 'none' that the analyst recorded as 'available').
    det_features = _build_feature_comparison(competitor_knowledge)
    if det_features:
        report.feature_comparison = det_features

    # Inject deterministic pricing table into markdown (replace or append).
    pricing_md = _build_pricing_markdown(competitor_knowledge, output_language)
    if pricing_md:
        if "## Pricing" in report.markdown_content or "## 定价" in report.markdown_content:
            report.markdown_content = re.sub(
                r"## (?:Pricing|定价).*?(?=\n## |\Z)",
                pricing_md + "\n\n",
                report.markdown_content,
                flags=re.DOTALL,
            )
        else:
            report.markdown_content = (
                report.markdown_content.rstrip() + "\n\n" + pricing_md
            )

    # Post-process: replace raw [src_xxx] tokens with deterministic [N] citations.
    report.markdown_content = render_report_markdown(report)
    return report


def run(
    db: Session,
    project_id: str,
    competitor_knowledge: list[CompetitorKnowledge],
    sources: list[SourceEvidence],
    goals: list[str],
    rework_hints: list[str] | None = None,
    output_language: str = "en",
    analysis_purpose: str = "general",
    custom_dimensions: list[str] | None = None,
) -> CompetitiveReport:
    """Generate a :class:`CompetitiveReport` from competitor knowledge."""
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    start = time.time()

    agent_run = AgentRun(
        agent_run_id=run_id,
        project_id=project_id,
        agent_name="WriterAgent",
        input={
            "competitor_count": len(competitor_knowledge),
            "source_count": len(sources),
            "goals": goals,
            "rework_hints": rework_hints or [],
            "output_language": output_language,
            "analysis_purpose": analysis_purpose,
            "custom_dimensions": custom_dimensions or [],
        },
        status=AgentRunStatus.running,
    )
    trace_service.save_agent_run(db, agent_run)

    try:
        if not competitor_knowledge:
            raise ValueError(
                "WriterAgent received no competitor knowledge; analyst must run first."
            )

        system_prompt = _load_prompt()
        if output_language == "zh":
            system_prompt += (
                "\n\nIMPORTANT — OUTPUT LANGUAGE: Simplified Chinese (简体中文).\n"
                "Write ALL user-facing text in Chinese: executive_summary[].text, "
                "strategic_recommendations[].text, markdown_content, and all display "
                "strings in pricing_comparison, user_persona_comparison, swot_comparison, "
                "and the report title.\n"
                "JSON keys, source_ids, competitor names, URLs, and enum values stay in English."
            )
        llm = _build_json_llm()

        user_message = _build_user_message(
            competitor_knowledge=competitor_knowledge,
            sources=sources,
            goals=goals,
            rework_hints=rework_hints,
            output_language=output_language,
            analysis_purpose=analysis_purpose,
            custom_dimensions=custom_dimensions,
        )
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ]
        report, is_fallback, token_usage = _produce_report(
            llm,
            messages,
            project_id=project_id,
            competitor_knowledge=competitor_knowledge,
            sources=sources,
            goals=goals,
        )
        report = _bind_report_fields(
            report,
            project_id=project_id,
            competitor_knowledge=competitor_knowledge,
            sources=sources,
            output_language=output_language,
        )
        report.analysis_purpose = analysis_purpose

        elapsed_ms = int((time.time() - start) * 1000)
        trace_service.update_agent_run(
            db,
            run_id,
            status=AgentRunStatus.success,
            output={
                "report_id": report.report_id,
                "executive_summary_claims": len(report.executive_summary),
                "recommendations": len(report.strategic_recommendations),
                "source_list_count": len(report.source_list),
                "is_fallback": is_fallback,
            },
            latency_ms=elapsed_ms,
            token_usage=token_usage,
        )
        if is_fallback:
            logger.warning(
                "WriterAgent: emitted FALLBACK report %s for project %s — "
                "QA should flag missing executive_summary/recommendations.",
                report.report_id,
                project_id,
            )
        else:
            logger.info(
                "WriterAgent: produced report %s for project %s",
                report.report_id,
                project_id,
            )
        return report

    except Exception as exc:
        elapsed_ms = int((time.time() - start) * 1000)
        trace_service.update_agent_run(
            db,
            run_id,
            status=AgentRunStatus.failed,
            error_message=str(exc),
            latency_ms=elapsed_ms,
        )
        logger.error("WriterAgent failed: %s", exc)
        raise
