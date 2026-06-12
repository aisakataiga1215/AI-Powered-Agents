"""WriterAgent.

Synthesizes a :class:`CompetitiveReport` from structured competitor
knowledge using function/tool calling when the provider supports it.
JSON Output remains as a compatibility fallback for OpenAI-compatible
providers whose function-calling implementation is incomplete.

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
from app.schemas.claim import Claim, Sentence
from app.schemas.knowledge import CompetitorKnowledge
from app.schemas.report import CompetitiveReport
from app.schemas.scoring import CompetitorScore, DimensionScore
from app.schemas.source import SourceEvidence
from app.schemas.trace import AgentRun, AgentRunStatus, TokenUsage
from app.services import trace_service
from app.services.markdown_renderer import render_report_markdown
from app.services.normalization_service import normalize_feature_category

logger = get_logger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "writer.md"
_MAX_SOURCE_TITLE_CHARS = 90
_MAX_REWORK_HINTS = 8
_RAW_RESPONSE_LOG_CHARS = 2000
_TRACE_PREVIEW_CHARS = 1200


def _preview(text: str, limit: int = _TRACE_PREVIEW_CHARS) -> str:
    normalized = " ".join((text or "").split())
    return normalized[:limit] + ("…" if len(normalized) > limit else "")


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _serialize_knowledge(knowledge: list[CompetitorKnowledge]) -> str:
    """Dump complete structured competitor knowledge for the writer prompt."""
    rendered: list[str] = []
    for ck in knowledge:
        payload = ck.model_dump(mode="json")
        text = json.dumps(payload, ensure_ascii=False)
        rendered.append(text)
    return "\n\n".join(rendered)


def _render_source_index(sources: list[SourceEvidence]) -> str:
    """Render a compact index of available source ids for the prompt."""
    if not sources:
        return "(no sources available)"
    lines = [
        f"- {s.source_id} | {s.competitor_name} | {s.source_type.value} | {_preview(s.title, _MAX_SOURCE_TITLE_CHARS)}"
        for s in sources
    ]
    return "\n".join(lines)


def _build_user_message(
    competitor_knowledge: list[CompetitorKnowledge],
    sources: list[SourceEvidence],
    goals: list[str],
    analysis_frameworks: list[str] | None = None,
    rework_hints: list[str] | None = None,
    output_language: str = "en",
    analysis_purpose: str = "unknown",
    custom_dimensions: list[str] | None = None,
) -> str:
    hints_section = ""
    if rework_hints:
        rendered_hints = "\n".join(f"- {hint}" for hint in rework_hints[:_MAX_REWORK_HINTS])
        if len(rework_hints) > _MAX_REWORK_HINTS:
            rendered_hints += f"\n- ... {len(rework_hints) - _MAX_REWORK_HINTS} more hints omitted"
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
        f'"analysis_frameworks": {json.dumps(analysis_frameworks or ["swot"])},\n'
        '"selected_report_tabs": report tab keys in final display order,\n'
        '"framework_sections": object containing only requested framework sections; use keys "three_c" and/or "aarrr" when requested,\n'
        '"custom_dimension_sections": object keyed by requested custom dimension names,\n'
        '"analysis_objective": "one-sentence statement of what this analysis accomplishes",\n'
        '"competitor_selection_rationale": {<comp_name>: "why included based on its role"},\n'
    )

    return (
        f"Report goals: {', '.join(goals) if goals else '(none)'}\n"
        f"Report frameworks: {', '.join(analysis_frameworks or ['swot'])}\n"
        f"Custom dimensions: {', '.join(custom_dimensions or []) if custom_dimensions else '(none)'}\n"
        f"{hints_section}\n"
        f"Available source ids (use these in claim evidence):\n"
        f"{_render_source_index(sources)}\n\n"
        f"Competitor knowledge (JSON, one per competitor):\n"
        f"{_serialize_knowledge(competitor_knowledge)}\n\n"
        f"{lang_instruction}"
        f"{purpose_instruction}"
        f"{_REPORT_CONCISION_INSTRUCTION}"
        "Return ONE JSON object matching the CompetitiveReport schema. "
        "Every executive_summary and strategic_recommendations entry MUST "
        "be an object with 'text', 'evidence' (list of source_ids), and "
        "'is_hypothesis'. Do not invent sources. Do not wrap the response "
        "in markdown fences."
    )


_REPORT_CONCISION_INSTRUCTION = """
Keep the report concise:
- Return at most 3 executive_summary claims and 3 strategic_recommendations.
- Keep each claim under 45 words.
- Leave markdown_content as an empty string; markdown is rendered deterministically.
- Generate framework and custom-dimension sections only inside CompetitiveReport fields.
- Do not generate pricing_comparison or feature_comparison.
"""


def _build_base_llm(*, json_mode: bool) -> ChatOpenAI:
    """Construct a ChatOpenAI client for structured report generation."""
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured; WriterAgent cannot run."
        )
    kwargs: dict = {
        "model": settings.default_model,
        "api_key": settings.openai_api_key,
        "temperature": 0,
    }
    if json_mode:
        # ``response_format`` is an OpenAI request param; ``model_kwargs``
        # is the langchain-openai escape hatch for forwarding it.
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    if settings.llm_disable_thinking:
        # ``extra_body`` is a first-class ChatOpenAI field; passing the
        # thinking-disable flag through ``model_kwargs`` would have the
        # OpenAI client reject it as an unknown argument.
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    return ChatOpenAI(**kwargs)


def _build_json_llm() -> ChatOpenAI:
    """Construct a ChatOpenAI client bound to JSON-object response mode."""
    return _build_base_llm(json_mode=True)


def _build_function_calling_llm():
    """Construct a structured-output client using native function calling."""
    return _build_base_llm(json_mode=False).with_structured_output(
        CompetitiveReport,
        method="function_calling",
        include_raw=True,
    )


def _extract_token_usage(response: Any) -> TokenUsage:
    """Extract token counts from a LangChain AIMessage response.

    LangChain stores usage in response.usage_metadata (preferred) or
    response.response_metadata["token_usage"]. Returns a zero TokenUsage
    if the provider does not return usage data.
    """
    # Preferred: LangChain's unified usage_metadata (dict with input_tokens, etc.)
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
    # Fallback: raw response_metadata from OpenAI-compatible providers
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
        return [{"text": value, "evidence": [], "is_hypothesis": True, "sentences": [{"text": value, "sources": []}]}]
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
                {"text": item, "evidence": [], "is_hypothesis": True, "sentences": [{"text": item, "sources": []}]}
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
        data["analysis_purpose"] = "unknown"
    if not isinstance(data.get("analysis_frameworks"), list):
        data["analysis_frameworks"] = ["swot"]
    if not isinstance(data.get("selected_report_tabs"), list):
        data["selected_report_tabs"] = []
    if not isinstance(data.get("framework_sections"), dict):
        data["framework_sections"] = {}
    if not isinstance(data.get("custom_dimension_sections"), dict):
        data["custom_dimension_sections"] = {}
    if not isinstance(data.get("purpose_sections"), dict):
        data["purpose_sections"] = {}
    if not isinstance(data.get("competitor_scores"), dict):
        data["competitor_scores"] = {}
    if not isinstance(data.get("analysis_objective"), str):
        data["analysis_objective"] = ""
    if not isinstance(data.get("competitor_selection_rationale"), dict):
        data["competitor_selection_rationale"] = {}

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


def _strip_invalid_sentence_sources(report: CompetitiveReport, valid_source_ids: set[str]) -> None:
    """Remove any sentence source IDs not in the input bundle (in-place).

    Prevents hallucinated citation IDs from propagating. Logs a warning
    when invalid IDs are found so the issue is visible in traces.
    """
    for claim in list(report.executive_summary) + list(report.strategic_recommendations):
        if not claim.sentences:
            continue
        for sentence in claim.sentences:
            invalid = [sid for sid in sentence.sources if sid not in valid_source_ids]
            if invalid:
                logger.warning(
                    "WriterAgent: stripped hallucinated source IDs from sentence: %s", invalid
                )
                sentence.sources = [sid for sid in sentence.sources if sid in valid_source_ids]


def _produce_report(
    llm: ChatOpenAI,
    messages: list,
    project_id: str,
    competitor_knowledge: list[CompetitorKnowledge],
    sources: list[SourceEvidence],
    goals: list[str],
) -> tuple[CompetitiveReport, bool, TokenUsage, str, str]:
    """Invoke the LLM, parse JSON, validate, fall back on any failure.

    Returns ``(report, is_fallback, token_usage, raw_preview, parse_status)`` so the caller can record
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
            "",
            "llm_error_fallback",
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
            _preview(content),
            "empty_response_fallback",
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
            _preview(content),
            "json_parse_error_fallback",
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
            _preview(content),
            "schema_validation_error_fallback",
        )

    return report, False, token_usage, _preview(content), "parsed"


def _produce_report_function_calling(
    llm: Any,
    messages: list,
) -> tuple[CompetitiveReport, TokenUsage, str, str]:
    """Invoke a function-calling structured-output LLM.

    Raises on provider/tool-call/parsing failure so the caller can fall back
    to JSON Output mode without marking the report as a true fallback.
    """
    response = llm.invoke(messages)
    raw_message = response.get("raw") if isinstance(response, dict) else None
    parsed = response.get("parsed") if isinstance(response, dict) else response
    parsing_error = response.get("parsing_error") if isinstance(response, dict) else None
    if parsing_error is not None:
        raise ValueError(f"function calling parse error: {parsing_error}")

    if isinstance(parsed, CompetitiveReport):
        report = parsed
    else:
        report = CompetitiveReport.model_validate(_normalize_report_payload(parsed))

    preview_payload = report.model_dump(mode="json")
    return (
        report,
        _extract_token_usage(raw_message),
        _preview(json.dumps(preview_payload, ensure_ascii=False)),
        "function_calling_parsed",
    )


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


def _selected_report_tabs(goals: list[str] | None, frameworks: list[str] | None, custom_dimensions: list[str] | None) -> list[str]:
    tabs = ["summary"]
    for goal in goals or []:
        if goal not in tabs:
            tabs.append(goal)
    for framework in frameworks or ["swot"]:
        if framework not in tabs:
            tabs.append(framework)
    for dim in custom_dimensions or []:
        key = f"custom_dimension:{dim}"
        if key not in tabs:
            tabs.append(key)
    if "recommendations" not in tabs:
        tabs.append("recommendations")
    tabs.append("qa")
    return tabs


def _build_framework_sections(
    knowledge: list[CompetitorKnowledge],
    frameworks: list[str] | None,
    output_language: str,
) -> dict:
    requested = set(frameworks or ["swot"])
    zh = output_language == "zh"
    names = [ck.competitor_name for ck in knowledge if ck.competitor_name]
    sections: dict[str, object] = {}
    if "three_c" in requested:
        sections["three_c"] = {
            "Customer" if not zh else "用户": [
                f"{ck.competitor_name}: " + (
                    "; ".join(p.name for p in ck.user_personas if p.name)
                    or "; ".join(c.text for c in (ck.product_profile.target_users if ck.product_profile else [])[:2])
                    or ("暂无足够证据" if zh else "Insufficient evidence")
                )
                for ck in knowledge
            ],
            "Company" if not zh else "公司": [
                f"{ck.competitor_name}: "
                + (ck.product_profile.positioning.text if ck.product_profile and ck.product_profile.positioning else ("暂无足够证据" if zh else "Insufficient evidence"))
                for ck in knowledge
            ],
            "Competitor" if not zh else "竞争": [
                ("覆盖竞品：" if zh else "Covered competitors: ") + ", ".join(names)
            ],
        }
    if "aarrr" in requested:
        placeholder = "暂无足够证据" if zh else "Insufficient evidence"
        sections["aarrr"] = {
            stage: [
                f"{ck.competitor_name}: {placeholder}"
                for ck in knowledge
            ]
            for stage in ["Acquisition", "Activation", "Retention", "Revenue", "Referral"]
        }
    return sections


def _build_custom_dimension_sections(
    knowledge: list[CompetitorKnowledge],
    custom_dimensions: list[str] | None,
    output_language: str,
) -> dict:
    if not custom_dimensions:
        return {}
    placeholder = "暂无足够证据" if output_language == "zh" else "Insufficient evidence"
    return {
        dim: [
            {
                "competitor_name": ck.competitor_name,
                "summary": placeholder,
                "evidence": _first_evidence(ck),
                "confidence": "low",
            }
            for ck in knowledge
        ]
        for dim in custom_dimensions
    }


_CHOOSE_PRODUCT_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("场景适配", 0.30),
    ("功能覆盖", 0.25),
    ("价格与试用", 0.20),
    ("风险与限制", 0.15),
    ("证据充分度", 0.10),
)


def _score_from_thresholds(value: int, thresholds: tuple[int, int, int, int]) -> int:
    if value >= thresholds[3]:
        return 5
    if value >= thresholds[2]:
        return 4
    if value >= thresholds[1]:
        return 3
    if value >= thresholds[0]:
        return 2
    return 1


def _feature_count(ck: CompetitorKnowledge) -> int:
    return sum(
        1
        for category in ck.feature_tree
        for feature in category.features
        if feature.name and feature.availability != "unknown"
    )


def _weakness_count(ck: CompetitorKnowledge) -> int:
    return len(ck.swot.weaknesses) if ck.swot else 0


def _dimension_confidence(evidence: list[str]) -> str:
    if len(evidence) >= 3:
        return "high"
    if len(evidence) >= 1:
        return "medium"
    return "low"


def _build_choose_product_scores(
    knowledge: list[CompetitorKnowledge],
) -> tuple[dict[str, CompetitorScore], dict]:
    scores: dict[str, CompetitorScore] = {}
    best_for: dict[str, str] = {}
    avoid: dict[str, str] = {}
    ranking: list[dict] = []
    decision_matrix: list[dict] = []

    for ck in knowledge:
        name = ck.competitor_name
        source_ids = _first_evidence(ck, limit=5) or list(ck.sources[:5])
        personas = [p.name for p in ck.user_personas if p.name]
        target_users = (
            [claim.text for claim in ck.product_profile.target_users]
            if ck.product_profile
            else []
        )
        feature_count = _feature_count(ck)
        plan_count = len(ck.pricing_model.plans) if ck.pricing_model else 0
        has_free = bool(ck.pricing_model and ck.pricing_model.has_free_plan)
        weakness_count = _weakness_count(ck)
        evidence_count = len(set(ck.sources or source_ids))

        fit_score = 5 if personas else 4 if target_users else 3
        feature_score = _score_from_thresholds(feature_count, (1, 3, 5, 8))
        pricing_score = 5 if has_free else 4 if plan_count >= 2 else 3 if plan_count == 1 else 2
        risk_score = 5 if weakness_count == 0 else 4 if weakness_count == 1 else 3 if weakness_count == 2 else 2
        evidence_score = _score_from_thresholds(evidence_count, (1, 2, 4, 6))

        raw_dimensions = [
            ("场景适配", fit_score, "用户画像或目标用户越明确，越容易判断是否适合当前使用场景。"),
            ("功能覆盖", feature_score, f"已识别 {feature_count} 个可用或受限功能。"),
            ("价格与试用", pricing_score, "有免费方案或清晰套餐时，采购和试用风险更低。"),
            ("风险与限制", risk_score, f"结构化 SWOT 中识别到 {weakness_count} 个主要弱点。"),
            ("证据充分度", evidence_score, f"当前绑定 {evidence_count} 个来源，来源越多评分越稳定。"),
        ]
        weights = dict(_CHOOSE_PRODUCT_WEIGHTS)
        dimensions = [
            DimensionScore(
                dimension_name=label,
                score=score,
                weight=weights[label],
                rationale=rationale,
                evidence=source_ids,
                source_confidence=_dimension_confidence(source_ids),
            )
            for label, score, rationale in raw_dimensions
        ]
        overall = sum(d.score * d.weight for d in dimensions) * 20
        scores[name] = CompetitorScore(
            competitor_name=name,
            overall_score=round(overall, 1),
            dimensions=dimensions,
        )

        best_for[name] = (
            f"适合 {', '.join(personas[:2])}。"
            if personas
            else (target_users[0] if target_users else "适合需要先验证核心能力的团队。")
        )
        avoid_reasons: list[str] = []
        if plan_count == 0:
            avoid_reasons.append("预算敏感或必须提前核验价格的团队")
        if feature_count < 3:
            avoid_reasons.append("需要成熟完整功能栈的重度用户")
        if weakness_count >= 2:
            avoid_reasons.append("对稳定性、限制和迁移风险敏感的团队")
        avoid[name] = "；".join(avoid_reasons) if avoid_reasons else "暂无明显不建议人群，但仍应核验关键来源。"

    ranked_names = sorted(scores, key=lambda n: scores[n].overall_score, reverse=True)
    for index, name in enumerate(ranked_names, start=1):
        ranking.append({
            "rank": index,
            "competitor_name": name,
            "overall_score": scores[name].overall_score,
            "summary": best_for.get(name, ""),
        })

    for label, weight in _CHOOSE_PRODUCT_WEIGHTS:
        row: dict[str, object] = {"criterion": label, "weight": weight}
        for name in ranked_names:
            dim = next((d for d in scores[name].dimensions if d.dimension_name == label), None)
            row[name] = f"{dim.score}/5" if dim else "—"
        decision_matrix.append(row)

    return scores, {
        "recommendation_ranking": ranking,
        "best_for": best_for,
        "who_should_avoid": avoid,
        "decision_matrix": decision_matrix,
        "scoring_weights": [
            {"dimension": label, "weight": weight}
            for label, weight in _CHOOSE_PRODUCT_WEIGHTS
        ],
    }


def _first_evidence(ck: CompetitorKnowledge, limit: int = 3) -> list[str]:
    """Return a compact list of source ids already attached to analyst claims."""
    seen: list[str] = []

    def add_many(ids: list[str]) -> None:
        for sid in ids:
            if sid and sid not in seen:
                seen.append(sid)

    if ck.product_profile:
        if ck.product_profile.positioning:
            add_many(list(ck.product_profile.positioning.evidence))
        for claim in ck.product_profile.target_users:
            add_many(list(claim.evidence))
    if ck.pricing_model and ck.pricing_model.summary:
        add_many(list(ck.pricing_model.summary.evidence))
    for cat in ck.feature_tree[:2]:
        for feature in cat.features[:2]:
            add_many(list(feature.evidence))
    return seen[:limit]


def _claim(text: str, evidence: list[str] | None = None, hypothesis: bool = False) -> Claim:
    return Claim(
        text=text,
        evidence=evidence or [],
        confidence="medium" if evidence else "low",
        is_hypothesis=hypothesis or not bool(evidence),
        created_by="WriterAgent",
    )


def _backfill_required_sections(
    report: CompetitiveReport,
    knowledge: list[CompetitorKnowledge],
    output_language: str,
) -> None:
    """Fill required top-level report sections from Analyst structured data.

    This is especially important on LLM fallback paths: the report should
    remain source-traceable and useful, while still clearly marked as fallback
    in markdown/trace.
    """
    zh = output_language == "zh"
    names = [ck.competitor_name for ck in knowledge if ck.competitor_name]
    evidence = _first_evidence(knowledge[0]) if knowledge else []

    if not report.executive_summary:
        if zh:
            report.executive_summary = [
                _claim(f"本次分析覆盖 {len(names)} 个竞品：{', '.join(names)}。", evidence),
                _claim("各产品在核心功能、用户体验、定价策略和生态建设方面存在差异化竞争。", evidence, hypothesis=True),
                _claim("由于部分 live 来源较弱或触发区域限制，低置信信息需要结合来源页人工复核。", evidence, hypothesis=True),
            ]
        else:
            report.executive_summary = [
                _claim(f"This analysis covers {len(names)} competitors: {', '.join(names)}.", evidence),
                _claim("Key differences cluster around core capabilities, user experience, pricing strategy, and ecosystem maturity.", evidence, hypothesis=True),
                _claim("Some live sources are weak or region-limited, so low-confidence findings should be manually verified against cited sources.", evidence, hypothesis=True),
            ]

    if not report.swot_comparison:
        swot: dict[str, dict] = {}
        for ck in knowledge:
            if ck.swot:
                swot[ck.competitor_name] = ck.swot.model_dump(mode="json")
        report.swot_comparison = swot

    if not report.user_persona_comparison:
        report.user_persona_comparison = {
            ck.competitor_name: ", ".join(p.name for p in ck.user_personas if p.name)
            for ck in knowledge
            if ck.user_personas
        }

    if not report.strategic_recommendations:
        if zh:
            report.strategic_recommendations = [
                _claim("优先选择与自身使用场景匹配的产品，而不是只看单一价格或模型能力。", evidence, hypothesis=True),
                _claim("对企业或团队场景，应重点核验隐私、SSO、审计、权限和用量管理能力。", evidence, hypothesis=True),
                _claim("对高频个人开发者，应重点比较上下文能力、Agent 限额、模型额度和超额计费。", evidence, hypothesis=True),
            ]
        else:
            report.strategic_recommendations = [
                _claim("Choose by usage scenario rather than by headline price or model access alone.", evidence, hypothesis=True),
                _claim("For teams or enterprises, verify privacy, SSO, audit, permissioning, and usage-management controls.", evidence, hypothesis=True),
                _claim("For high-frequency individual developers, compare context quality, agent limits, model credits, and overage pricing.", evidence, hypothesis=True),
            ]


def _bind_report_fields(
    report: CompetitiveReport,
    project_id: str,
    competitor_knowledge: list[CompetitorKnowledge],
    sources: list[SourceEvidence],
    output_language: str = "en",
    goals: list[str] | None = None,
    analysis_frameworks: list[str] | None = None,
    analysis_purpose: str = "unknown",
    custom_dimensions: list[str] | None = None,
) -> CompetitiveReport:
    """Backfill fields the LLM commonly omits or fills incorrectly."""
    report.project_id = project_id
    report.analysis_purpose = analysis_purpose
    report.analysis_frameworks = analysis_frameworks or ["swot"]
    report.selected_report_tabs = _selected_report_tabs(goals, report.analysis_frameworks, custom_dimensions)
    if analysis_purpose == "choose_product" and "scoring" not in report.selected_report_tabs:
        insert_at = report.selected_report_tabs.index("recommendations") if "recommendations" in report.selected_report_tabs else len(report.selected_report_tabs)
        report.selected_report_tabs.insert(insert_at, "scoring")
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

    _backfill_required_sections(report, competitor_knowledge, output_language)
    generated_framework_sections = _build_framework_sections(
        competitor_knowledge,
        report.analysis_frameworks,
        output_language,
    )
    report.framework_sections = {
        **generated_framework_sections,
        **(report.framework_sections or {}),
    }
    generated_custom_sections = _build_custom_dimension_sections(
        competitor_knowledge,
        custom_dimensions,
        output_language,
    )
    report.custom_dimension_sections = {
        **generated_custom_sections,
        **(report.custom_dimension_sections or {}),
    }
    if analysis_purpose == "choose_product":
        generated_scores, generated_purpose = _build_choose_product_scores(
            competitor_knowledge
        )
        report.competitor_scores = {
            **generated_scores,
            **(report.competitor_scores or {}),
        }
        report.purpose_sections = {
            **generated_purpose,
            **(report.purpose_sections or {}),
        }

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
    analysis_frameworks: list[str] | None = None,
    rework_hints: list[str] | None = None,
    output_language: str = "en",
    analysis_purpose: str = "unknown",
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
            "analysis_frameworks": analysis_frameworks or ["swot"],
            "rework_hints": rework_hints or [],
            "output_language": output_language,
            "analysis_purpose": analysis_purpose,
            "custom_dimensions": custom_dimensions or [],
            "decision_summary": "Write a cited competitive report from structured knowledge.",
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
        user_message = _build_user_message(
            competitor_knowledge=competitor_knowledge,
            sources=sources,
            goals=goals,
            analysis_frameworks=analysis_frameworks,
            rework_hints=rework_hints,
            output_language=output_language,
            analysis_purpose=analysis_purpose,
            custom_dimensions=custom_dimensions,
        )
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ]
        is_fallback = False
        try:
            report, token_usage, llm_output_preview, parse_status = _produce_report_function_calling(
                _build_function_calling_llm(),
                messages,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "WriterAgent: function calling failed: %s; falling back to JSON output.",
                exc,
            )
            report, is_fallback, token_usage, llm_output_preview, parse_status = _produce_report(
                _build_json_llm(),
                messages,
                project_id=project_id,
                competitor_knowledge=competitor_knowledge,
                sources=sources,
                goals=goals,
            )
        valid_source_ids = {s.source_id for s in sources}
        _strip_invalid_sentence_sources(report, valid_source_ids)
        report = _bind_report_fields(
            report,
            project_id=project_id,
            competitor_knowledge=competitor_knowledge,
            sources=sources,
            output_language=output_language,
            goals=goals,
            analysis_frameworks=analysis_frameworks or ["swot"],
            analysis_purpose=analysis_purpose,
            custom_dimensions=custom_dimensions or [],
        )

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
                "decision_summary": (
                    f"Generated report {report.report_id} with {len(report.executive_summary)} summary claims."
                ),
                "prompt_preview": _preview(user_message),
                "llm_output_preview": llm_output_preview,
                "parse_status": parse_status,
            },
            latency_ms=elapsed_ms,
            token_usage=token_usage,
        )
        if is_fallback:
            logger.warning(
                "WriterAgent: emitted FALLBACK report %s for project %s — "
                "deterministic backfills were applied before QA.",
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
