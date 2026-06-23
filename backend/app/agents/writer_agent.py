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
from app.schemas.pm_sections import FeatureInsights, MarketBackground, OperationMonetization
from app.schemas.report import CompetitiveReport
from app.schemas.scoring import CompetitorScore, DimensionScore, OpportunityDimension, OpportunityScore
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
_PARAMETER_TAG_RE = re.compile(r"</?parameter[^>]*>", re.IGNORECASE)


def _clean_function_call_artifacts(value: str) -> str:
    """Remove leaked tool/function-call parameter fragments from display text."""
    text = str(value or "").strip()
    if not text:
        return ""
    markers = [idx for idx in (text.find("<parameter"), text.find("</parameter")) if idx >= 0]
    if markers:
        text = text[: min(markers)]
    return _PARAMETER_TAG_RE.sub("", text).strip()


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
        '"custom_dimension_analysis": scored evidence objects keyed by requested custom dimension names,\n'
        '"opportunity_score": build_product-only opportunity score object, otherwise null,\n'
        '"market_background", "feature_insights", and "operation_monetization": only for understand_industry or analyze_growth_ops,\n'
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
    if not isinstance(data.get("custom_dimension_analysis"), dict):
        data["custom_dimension_analysis"] = {}
    if not isinstance(data.get("purpose_sections"), dict):
        data["purpose_sections"] = {}
    if not isinstance(data.get("competitor_scores"), dict):
        data["competitor_scores"] = {}
    if not isinstance(data.get("opportunity_score"), dict):
        data["opportunity_score"] = None
    for key in ("market_background", "feature_insights", "operation_monetization"):
        if not isinstance(data.get(key), dict):
            data[key] = None
    if not isinstance(data.get("analysis_objective"), str):
        data["analysis_objective"] = ""
    data["analysis_objective"] = _clean_function_call_artifacts(data["analysis_objective"])
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
        # Accumulate features per normalized capability bucket before building
        # the string. Raw LLM categories are often product-specific ("Cascade",
        # "Composer", "TRAE Work"), so using them directly makes the UI look
        # like a list of one-off rows instead of a horizontal comparison.
        merged: dict[str, list[str]] = {}
        for cat in ck.feature_tree:
            for feature in cat.features:
                if feature.availability == "unknown" or not feature.name:
                    continue
                bucket = _feature_capability_bucket(cat.category, feature.name, feature.description)
                merged.setdefault(bucket, [])
                if feature.name not in merged[bucket]:
                    merged[bucket].append(feature.name)
        cat_parts = [
            f"{canonical}: {', '.join(names)}"
            for canonical, names in _ordered_feature_buckets(merged).items()
            if names
        ]
        if cat_parts:
            result[ck.competitor_name] = " | ".join(cat_parts)
    return result


_FEATURE_BUCKETS = [
    "代码补全与生成",
    "Agent 工作流",
    "IDE / 编辑器体验",
    "代码库理解与搜索",
    "评审与质量",
    "团队协作",
    "企业安全与管理",
    "集成 / API / 扩展",
    "云任务与部署",
]


def _feature_capability_bucket(category: str, name: str, description: str = "") -> str:
    text = f"{category} {name} {description}".lower()
    if any(k in text for k in ["review", "bug", "quality", "test", "debug"]):
        return "评审与质量"
    if any(k in text for k in ["sso", "saml", "oidc", "scim", "audit", "rbac", "privacy", "security", "admin", "permission", "governance"]):
        return "企业安全与管理"
    if any(k in text for k in ["team", "collaboration", "shared", "billing", "analytics", "marketplace"]):
        return "团队协作"
    if any(k in text for k in ["autocomplete", "completion", "generate", "chat", "command", "prompt"]):
        return "代码补全与生成"
    if any(k in text for k in ["search", "navigation", "context", "index", "codebase", "semantic"]):
        return "代码库理解与搜索"
    if any(k in text for k in ["api", "mcp", "plugin", "extension", "integration", "vscode", "vs code"]):
        return "集成 / API / 扩展"
    if any(k in text for k in ["deploy", "cloud", "remote", "workspace", "preview"]):
        return "云任务与部署"
    if any(k in text for k in ["agent", "composer", "cascade", "session", "delegate", "task"]):
        return "Agent 工作流"
    normalized = normalize_feature_category(category)
    if normalized != category:
        return normalized
    return "IDE / 编辑器体验"


def _ordered_feature_buckets(merged: dict[str, list[str]]) -> dict[str, list[str]]:
    ordered: dict[str, list[str]] = {}
    for bucket in _FEATURE_BUCKETS:
        if bucket in merged:
            ordered[bucket] = merged[bucket]
    for bucket, names in merged.items():
        if bucket not in ordered:
            ordered[bucket] = names
    return ordered


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
    placeholder = "未在已采集来源中找到该维度的直接表述" if output_language == "zh" else "No direct statement for this dimension was found in collected sources"
    return {
        dim: [
            _build_custom_dimension_entry(ck, dim, placeholder)
            for ck in knowledge
        ]
        for dim in custom_dimensions
    }


def _dimension_keywords(dimension: str) -> tuple[str, ...]:
    lower = dimension.lower()
    keyword_map: dict[str, tuple[str, ...]] = {
        "隐私": ("隐私", "privacy", "private", "数据", "data", "训练", "training", "保留", "retention", "隔离", "isolation"),
        "本地部署": ("本地", "本地部署", "私有化", "私有部署", "on-prem", "on premise", "self-host", "self host", "local deployment"),
        "安全合规": ("安全", "合规", "security", "compliance", "sso", "权限", "permission", "审计", "audit", "soc", "iso", "gdpr"),
        "企业版": ("企业", "enterprise", "team", "团队", "sso", "权限", "审计", "admin"),
        "价格": ("价格", "定价", "pricing", "price", "cost", "费用", "付费", "subscription"),
    }
    keywords: list[str] = [dimension, lower]
    for key, values in keyword_map.items():
        if key in dimension or key.lower() in lower:
            keywords.extend(values)
    return tuple(dict.fromkeys(k.lower() for k in keywords if k))


def _claim_text_and_evidence(claim: Claim | None) -> tuple[str, list[str]]:
    if claim is None:
        return "", []
    return claim.text or "", list(claim.evidence or [])


def _dimension_candidate_texts(ck: CompetitorKnowledge) -> list[tuple[str, list[str]]]:
    candidates: list[tuple[str, list[str]]] = []
    if ck.product_profile:
        candidates.append(_claim_text_and_evidence(ck.product_profile.positioning))
        for claim in ck.product_profile.target_users:
            candidates.append(_claim_text_and_evidence(claim))
    if ck.pricing_model:
        candidates.append(_claim_text_and_evidence(ck.pricing_model.summary))
        for plan in ck.pricing_model.plans:
            plan_text = " ".join([plan.name, plan.price, plan.billing_cycle, *list(plan.features or [])])
            candidates.append((plan_text, list(plan.evidence or [])))
    for category in ck.feature_tree:
        for feature in category.features:
            candidates.append((
                " ".join([category.category, feature.name, feature.description, feature.availability]),
                list(feature.evidence or []),
            ))
    for persona in ck.user_personas:
        candidates.append((
            " ".join([persona.name, persona.description, *list(persona.needs or []), *list(persona.pain_points or [])]),
            list(persona.evidence or []),
        ))
    if ck.user_feedback_summary:
        candidates.append((ck.user_feedback_summary.summary, list(ck.sources or [])))
        for claim in ck.user_feedback_summary.positive_points + ck.user_feedback_summary.negative_points:
            candidates.append(_claim_text_and_evidence(claim))
    if ck.swot:
        for claim in ck.swot.strengths + ck.swot.weaknesses + ck.swot.opportunities + ck.swot.threats:
            candidates.append(_claim_text_and_evidence(claim))
    return [(text.strip(), evidence) for text, evidence in candidates if text and text.strip()]


def _build_custom_dimension_entry(
    ck: CompetitorKnowledge,
    dimension: str,
    placeholder: str,
) -> dict:
    keywords = _dimension_keywords(dimension)
    matches: list[tuple[str, list[str]]] = []
    for text, evidence in _dimension_candidate_texts(ck):
        lower = text.lower()
        if any(keyword in lower for keyword in keywords):
            matches.append((text, evidence))

    evidence: list[str] = []
    for _text, ids in matches:
        for sid in ids:
            if sid and sid not in evidence:
                evidence.append(sid)
        if len(evidence) >= 5:
            break

    if matches:
        first_text = matches[0][0]
        summary = first_text[:220].rstrip()
        confidence = "medium" if evidence else "low"
    else:
        summary = placeholder
        evidence = _first_evidence(ck)
        confidence = "low"

    return {
        "competitor_name": ck.competitor_name,
        "summary": summary,
        "evidence": evidence,
        "confidence": confidence,
    }


def _build_custom_dimension_analysis(
    knowledge: list[CompetitorKnowledge],
    custom_dimensions: list[str] | None,
    output_language: str,
) -> dict[str, DimensionScore]:
    if not custom_dimensions:
        return {}
    placeholder = "已根据结构化知识和引用来源生成维度判断。" if output_language == "zh" else "Generated from structured knowledge and cited sources."
    result: dict[str, DimensionScore] = {}
    weight = round(1 / len(custom_dimensions), 3)
    for dim in custom_dimensions:
        entries = [
            _build_custom_dimension_entry(
                ck,
                dim,
                "未在已采集来源中找到该维度的直接表述" if output_language == "zh" else "No direct statement for this dimension was found in collected sources",
            )
            for ck in knowledge
        ]
        evidence: list[str] = []
        matched = 0
        for entry in entries:
            if entry.get("confidence") != "low":
                matched += 1
            for sid in entry.get("evidence", []):
                if sid and sid not in evidence:
                    evidence.append(sid)
            if len(evidence) >= 6:
                break
        confidence = "high" if matched >= max(2, len(knowledge) // 2) else ("medium" if matched else _dimension_confidence(evidence))
        score = 4 if matched else 2
        result[dim] = DimensionScore(
            dimension_name=dim,
            score=score,
            weight=weight,
            rationale=placeholder if matched else ("需要补充该维度的直接来源。" if output_language == "zh" else "Add direct sources for this dimension."),
            evidence=evidence[:6],
            source_confidence=confidence,
        )
    return result


_CHOOSE_PRODUCT_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("场景适配", 0.22),
    ("核心能力覆盖", 0.24),
    ("价格价值", 0.22),
    ("成熟度与可信度", 0.17),
    ("风险控制", 0.15),
)

_BUILD_PRODUCT_OPPORTUNITY_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("差异化空间", 0.30),
    ("功能缺口", 0.25),
    ("商业化清晰度", 0.20),
    ("进入风险", 0.15),
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


def _threat_count(ck: CompetitorKnowledge) -> int:
    return len(ck.swot.threats) if ck.swot else 0


def _first_paid_price(ck: CompetitorKnowledge) -> float | None:
    if not ck.pricing_model:
        return None
    prices: list[float] = []
    for plan in ck.pricing_model.plans:
        raw = (plan.price or "").lower()
        if "free" in raw or raw.strip() in {"$0", "0"}:
            continue
        match = re.search(r"\$?\s*(\d+(?:\.\d+)?)", raw)
        if match:
            prices.append(float(match.group(1)))
    return min(prices) if prices else None


def _has_enterprise_controls(ck: CompetitorKnowledge) -> bool:
    text = " ".join(
        [
            feature.name + " " + feature.description
            for category in ck.feature_tree
            for feature in category.features
        ]
    ).lower()
    return any(k in text for k in ["sso", "saml", "oidc", "scim", "audit", "rbac", "enterprise", "admin"])


def _capability_bucket_count(ck: CompetitorKnowledge) -> int:
    buckets: set[str] = set()
    for category in ck.feature_tree:
        for feature in category.features:
            if feature.name and feature.availability != "unknown":
                buckets.add(_feature_capability_bucket(category.category, feature.name, feature.description))
    return len(buckets)


def _dimension_confidence(evidence: list[str]) -> str:
    if len(evidence) >= 3:
        return "high"
    if len(evidence) >= 1:
        return "medium"
    return "low"


def _score_relative(value: float, values: list[float], *, higher_is_better: bool = True) -> int:
    if not values:
        return 3
    unique = sorted(set(values))
    if len(unique) == 1:
        return 3
    low, high = min(unique), max(unique)
    ratio = (value - low) / (high - low)
    if not higher_is_better:
        ratio = 1 - ratio
    if ratio >= 0.85:
        return 5
    if ratio >= 0.60:
        return 4
    if ratio >= 0.35:
        return 3
    if ratio >= 0.15:
        return 2
    return 1


def _build_choose_product_scores(
    knowledge: list[CompetitorKnowledge],
    custom_dimensions: list[str] | None = None,
) -> tuple[dict[str, CompetitorScore], dict]:
    scores: dict[str, CompetitorScore] = {}
    best_for: dict[str, str] = {}
    avoid: dict[str, str] = {}
    ranking: list[dict] = []
    decision_matrix: list[dict] = []
    feature_counts_by_name = {ck.competitor_name: _feature_count(ck) for ck in knowledge}
    bucket_counts_by_name = {ck.competitor_name: _capability_bucket_count(ck) for ck in knowledge}
    paid_prices_by_name = {ck.competitor_name: _first_paid_price(ck) for ck in knowledge}
    valid_paid_prices = [price for price in paid_prices_by_name.values() if price is not None]
    source_counts_by_name = {ck.competitor_name: len(set(ck.sources)) for ck in knowledge}
    risk_counts_by_name = {
        ck.competitor_name: _weakness_count(ck) + _threat_count(ck)
        for ck in knowledge
    }

    custom_dimensions = [dim for dim in (custom_dimensions or []) if str(dim).strip()]
    if custom_dimensions:
        base_weights = [(label, round(weight * 0.75, 3)) for label, weight in _CHOOSE_PRODUCT_WEIGHTS]
        custom_weight = round(0.25 / len(custom_dimensions), 3)
        scoring_weights = base_weights + [(dim, custom_weight) for dim in custom_dimensions]
    else:
        scoring_weights = list(_CHOOSE_PRODUCT_WEIGHTS)

    for ck in knowledge:
        name = ck.competitor_name
        source_ids = _first_evidence(ck, limit=5) or list(ck.sources[:5])
        personas = [p.name for p in ck.user_personas if p.name]
        target_users = (
            [claim.text for claim in ck.product_profile.target_users]
            if ck.product_profile
            else []
        )
        feature_count = feature_counts_by_name[name]
        bucket_count = bucket_counts_by_name[name]
        plan_count = len(ck.pricing_model.plans) if ck.pricing_model else 0
        has_free = bool(ck.pricing_model and ck.pricing_model.has_free_plan)
        paid_price = paid_prices_by_name[name]
        evidence_count = source_counts_by_name[name]
        risk_count = risk_counts_by_name[name]

        persona_signal = len(personas) or len(target_users)
        fit_score = min(5, 2 + min(persona_signal, 3))
        if any("enterprise" in p.lower() or "team" in p.lower() for p in personas + target_users):
            fit_score = min(5, fit_score + 1)

        feature_score = round(
            (
                _score_relative(feature_count, list(feature_counts_by_name.values()))
                + _score_relative(bucket_count, list(bucket_counts_by_name.values()))
            )
            / 2
        )

        if paid_price is None:
            pricing_score = 2 if has_free else 1
        else:
            pricing_score = _score_relative(paid_price, valid_paid_prices, higher_is_better=False)
            if has_free:
                pricing_score = min(5, pricing_score + 1)
            if plan_count >= 5 and paid_price <= 20:
                pricing_score = min(5, pricing_score + 1)
            if paid_price >= 50:
                pricing_score = max(1, pricing_score - 1)

        maturity_score = _score_relative(evidence_count, list(source_counts_by_name.values()))
        if _has_enterprise_controls(ck):
            maturity_score = min(5, maturity_score + 1)
        if ck.pricing_model and ck.pricing_model.summary:
            maturity_score = min(5, maturity_score + 1)

        risk_score = _score_relative(risk_count, list(risk_counts_by_name.values()), higher_is_better=False)
        if paid_price and paid_price >= 100:
            risk_score = max(1, risk_score - 1)
        if "credit" in ((ck.pricing_model.summary.text if ck.pricing_model and ck.pricing_model.summary else "")).lower():
            risk_score = max(1, risk_score - 1)

        custom_entries = {
            dim: _build_custom_dimension_entry(
                ck,
                dim,
                "未在已采集来源中找到该维度的直接表述",
            )
            for dim in custom_dimensions
        }
        custom_dimension_scores = []
        for dim, entry in custom_entries.items():
            matched = entry.get("confidence") != "low"
            dim_evidence = list(entry.get("evidence") or source_ids)
            custom_dimension_scores.append((
                dim,
                4 if matched else 2,
                (
                    str(entry.get("summary") or "")[:160]
                    if matched
                    else "缺少该自定义维度的直接来源，建议补充官方文档或用户研究。"
                ),
                dim_evidence[:5],
            ))

        base_dimensions: list[tuple[str, int, str]] = [
            ("场景适配", fit_score, "用户画像、目标用户和团队/企业适配度越明确，分数越高。"),
            ("核心能力覆盖", feature_score, f"识别到 {feature_count} 个功能，覆盖 {bucket_count} 个横向能力桶。"),
            ("价格价值", pricing_score, f"首个付费档约 {paid_price if paid_price is not None else '未知'} 美元/月，{'有' if has_free else '无'}免费档。"),
            ("成熟度与可信度", maturity_score, f"绑定 {evidence_count} 个来源，并结合企业控制、定价摘要等成熟度信号。"),
            ("风险控制", risk_score, f"SWOT 中识别到 {risk_count} 个弱点/威胁；高价或复杂 credit 计费会扣分。"),
        ]
        raw_dimensions: list[tuple[str, int, str, list[str]]] = [
            (label, score, rationale, source_ids)
            for label, score, rationale in base_dimensions
        ] + custom_dimension_scores
        weights = dict(scoring_weights)
        dimensions = [
            DimensionScore(
                dimension_name=label,
                score=score,
                weight=weights[label],
                rationale=rationale,
                evidence=evidence,
                source_confidence=_dimension_confidence(evidence),
            )
            for label, score, rationale, evidence in raw_dimensions
        ]
        overall = sum(d.score * d.weight for d in dimensions) * 20
        scores[name] = CompetitorScore(
            competitor_name=name,
            overall_score=round(overall, 1),
            dimensions=dimensions,
        )

        strengths: list[str] = []
        if fit_score >= 4:
            strengths.append("目标用户/场景匹配较清晰")
        if feature_score >= 4:
            strengths.append("核心能力覆盖较完整")
        if pricing_score >= 4:
            strengths.append("价格价值较好")
        if maturity_score >= 4:
            strengths.append("来源覆盖和成熟度较高")
        for dim, entry in custom_entries.items():
            if entry.get("confidence") != "low":
                strengths.append(f"{dim}维度有可引用证据")
        audience = "、".join(personas[:2] or target_users[:2])
        if audience:
            best_for[name] = f"适合{audience}；主要依据：{'；'.join(strengths[:3]) if strengths else '仍需结合关键来源复核'}。"
        else:
            best_for[name] = f"适合已明确采购/试用场景、愿意复核关键来源的团队；主要依据：{'；'.join(strengths[:3]) if strengths else '证据仍偏弱'}。"
        avoid_reasons: list[str] = []
        if plan_count == 0:
            avoid_reasons.append("预算敏感或必须提前核验价格的团队")
        if feature_count < 3:
            avoid_reasons.append("需要成熟完整功能栈的重度用户")
        if risk_count >= 3:
            avoid_reasons.append("对稳定性、限制和迁移风险敏感的团队")
        missing_custom = [dim for dim, entry in custom_entries.items() if entry.get("confidence") == "low"]
        if missing_custom:
            avoid_reasons.append(f"强依赖{', '.join(missing_custom[:2])}明确承诺的团队")
        avoid[name] = "；".join(avoid_reasons) if avoid_reasons else "暂无明显不建议人群，但仍应核验关键来源。"

    ranked_names = sorted(scores, key=lambda n: scores[n].overall_score, reverse=True)
    for index, name in enumerate(ranked_names, start=1):
        ranking.append({
            "rank": index,
            "competitor_name": name,
            "overall_score": scores[name].overall_score,
            "summary": best_for.get(name, ""),
        })

    for label, weight in scoring_weights:
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
            for label, weight in scoring_weights
        ],
    }


def _build_product_opportunity(
    knowledge: list[CompetitorKnowledge],
    output_language: str,
) -> tuple[OpportunityScore, dict]:
    zh = output_language == "zh"
    all_evidence: list[str] = []
    feature_counts: list[int] = []
    weakness_total = 0
    opportunity_claims: list[str] = []
    threat_claims: list[str] = []
    monetization_signals = 0

    for ck in knowledge:
        feature_counts.append(_feature_count(ck))
        weakness_total += _weakness_count(ck)
        if ck.pricing_model and ck.pricing_model.plans:
            monetization_signals += 1
        if ck.swot:
            opportunity_claims.extend(claim.text for claim in ck.swot.opportunities[:2])
            threat_claims.extend(claim.text for claim in ck.swot.threats[:2])
        for sid in _first_evidence(ck, limit=4) or list(ck.sources[:4]):
            if sid and sid not in all_evidence:
                all_evidence.append(sid)

    evidence = all_evidence[:8]
    max_features = max(feature_counts) if feature_counts else 0
    min_features = min(feature_counts) if feature_counts else 0
    spread = max_features - min_features
    weights = dict(_BUILD_PRODUCT_OPPORTUNITY_WEIGHTS)
    raw_dimensions = [
        ("差异化空间", _score_from_thresholds(len(opportunity_claims) + spread, (1, 2, 4, 6)), "竞品能力差异和机会描述越多，越容易找到可切入定位。"),
        ("功能缺口", _score_from_thresholds(spread + weakness_total, (1, 2, 4, 7)), "竞品功能覆盖不均或弱点越明显，越可能形成 MVP 切口。"),
        ("商业化清晰度", _score_from_thresholds(monetization_signals, (1, 2, 3, 4)), "越多竞品披露套餐或收费方式，说明商业化路径越可参考。"),
        ("进入风险", max(1, 6 - _score_from_thresholds(len(threat_claims) + weakness_total, (1, 2, 4, 7))), "威胁和弱点越集中，进入风险越高，该维度分数相应降低。"),
        ("证据充分度", _score_from_thresholds(len(evidence), (1, 2, 4, 6)), f"当前机会判断绑定 {len(evidence)} 个来源。"),
    ]
    dimensions = [
        OpportunityDimension(
            dimension_name=label,
            score=score,
            weight=weights[label],
            rationale=rationale,
            evidence=evidence,
            source_confidence=_dimension_confidence(evidence),
        )
        for label, score, rationale in raw_dimensions
    ]
    overall = round(sum(dim.score * dim.weight for dim in dimensions) * 20, 1)
    opportunity_score = OpportunityScore(
        overall_score=overall,
        dimensions=dimensions,
        scoring_note=(
            "机会评分是基于已采集竞品证据的方向性判断，用于产品规划，不代表客观市场规模。"
            if zh
            else "Opportunity scores are directional estimates for product planning based on the collected competitive evidence."
        ),
    )
    market_gaps = (
        _build_zh_market_gaps(
            feature_spread=spread,
            weakness_total=weakness_total,
            monetization_signals=monetization_signals,
            evidence_count=len(evidence),
        )
        if zh
        else opportunity_claims[:5] or ["Insufficient evidence; add user interviews or competitor community feedback."]
    )
    pitfalls = (
        _build_zh_pitfalls(
            threat_count=len(threat_claims),
            weakness_total=weakness_total,
            monetization_signals=monetization_signals,
        )
        if zh
        else threat_claims[:5] or ["Avoid copying surface-level competitor features without enough evidence."]
    )
    purpose_sections = {
        "opportunity_summary": {
            "overall_score": overall,
            "summary": (
                "适合从明确用户场景、功能缺口和商业化路径交集处寻找切入点。"
                if zh
                else "Look for entry points where user scenarios, feature gaps, and monetization paths overlap."
            ),
        },
        "market_gaps": market_gaps,
        "features_to_learn_from": [
            {
                "competitor_name": ck.competitor_name,
                "features": [
                    feature.name
                    for category in ck.feature_tree[:2]
                    for feature in category.features[:3]
                    if feature.name
                ][:5],
            }
            for ck in knowledge
        ],
        "pitfalls_to_avoid": pitfalls,
        "mvp_direction": (
            "优先验证一个高频、证据充分、竞品体验仍有缺口的核心工作流。"
            if zh
            else "Validate one high-frequency workflow with enough evidence and a visible competitor experience gap first."
        ),
    }
    return opportunity_score, purpose_sections


def _build_zh_market_gaps(
    *,
    feature_spread: int,
    weakness_total: int,
    monetization_signals: int,
    evidence_count: int,
) -> list[str]:
    gaps = [
        "从高频但体验仍不稳定的开发工作流切入，而不是直接复制头部工具的完整功能栈。",
    ]
    if feature_spread > 0:
        gaps.append("竞品功能覆盖存在差异，可优先寻找覆盖不足但用户频繁使用的能力切口。")
    if weakness_total > 0:
        gaps.append("把竞品 SWOT 中反复出现的弱点转化为产品定位，例如价格理解成本、平台覆盖或团队管理体验。")
    if monetization_signals > 0:
        gaps.append("主流竞品已有付费路径，新产品应在套餐边界、用量规则和试用门槛上降低决策成本。")
    if evidence_count < 4:
        gaps.append("当前证据仍偏少，进入前需要补充用户访谈、社区反馈或真实使用记录。")
    return gaps[:5]


def _build_zh_pitfalls(
    *,
    threat_count: int,
    weakness_total: int,
    monetization_signals: int,
) -> list[str]:
    pitfalls = [
        "避免只做功能清单式跟随，必须先证明目标用户愿意为具体工作流改善付费。",
        "避免在核心体验未验证前过早堆叠 Agent、模型和插件能力。",
    ]
    if threat_count > 0:
        pitfalls.append("注意头部竞品和大厂工具的快速跟进风险，差异化需要绑定明确场景。")
    if weakness_total > 0:
        pitfalls.append("不要重复竞品已有负反馈，尤其是复杂计费、平台限制和迁移成本。")
    if monetization_signals > 0:
        pitfalls.append("商业化设计要避免额度规则过复杂，否则容易在试用到付费阶段流失。")
    return pitfalls[:5]


def _build_pm_sections(
    knowledge: list[CompetitorKnowledge],
    analysis_purpose: str,
    output_language: str,
) -> tuple[MarketBackground | None, FeatureInsights | None, OperationMonetization | None, dict]:
    if analysis_purpose not in {"understand_industry", "analyze_growth_ops"}:
        return None, None, None, {}

    zh = output_language == "zh"
    names = [ck.competitor_name for ck in knowledge if ck.competitor_name]
    evidence_count = len({sid for ck in knowledge for sid in ck.sources})
    overview = (
        f"本次行业分析覆盖 {len(names)} 个产品，基于 {evidence_count} 个来源梳理市场背景、能力共性与商业化模式。"
        if zh
        else f"This industry analysis covers {len(names)} products and uses {evidence_count} sources to summarize market context, common capabilities, and monetization patterns."
    )
    strengths: list[str] = []
    opportunities: list[str] = []
    threats: list[str] = []
    monetization: list[str] = []
    differentiators: dict[str, list[str]] = {}
    table_stakes: dict[str, int] = {}
    gtm_profiles: dict[str, str] = {}

    for ck in knowledge:
        if ck.swot:
            strengths.extend(claim.text for claim in ck.swot.strengths[:2])
            opportunities.extend(claim.text for claim in ck.swot.opportunities[:2])
            threats.extend(claim.text for claim in ck.swot.threats[:2])
        feature_names = [
            feature.name
            for category in ck.feature_tree[:3]
            for feature in category.features[:4]
            if feature.name
        ]
        differentiators[ck.competitor_name] = feature_names[:6]
        for name in feature_names[:8]:
            table_stakes[name] = table_stakes.get(name, 0) + 1
        if ck.pricing_model and ck.pricing_model.plans:
            monetization.append(
                f"{ck.competitor_name}: {len(ck.pricing_model.plans)} pricing plan(s)"
            )
        if ck.product_profile and ck.product_profile.positioning:
            gtm_profiles[ck.competitor_name] = ck.product_profile.positioning.text
        else:
            gtm_profiles[ck.competitor_name] = "暂无足够证据" if zh else "Insufficient evidence"

    common_features = [
        name
        for name, count in sorted(table_stakes.items(), key=lambda item: item[1], reverse=True)
        if count > 1
    ][:8]
    if not common_features:
        common_features = list(table_stakes.keys())[:6]

    market_background = MarketBackground(
        market_overview=overview,
        key_trends=(strengths[:5] or (["暂无足够证据"] if zh else ["Insufficient evidence"])),
        growth_drivers=(opportunities[:5] or (["暂无足够证据"] if zh else ["Insufficient evidence"])),
        market_challenges=(threats[:5] or (["暂无足够证据"] if zh else ["Insufficient evidence"])),
    )
    feature_insights = FeatureInsights(
        table_stakes=common_features,
        differentiators=differentiators,
        feature_gaps=opportunities[:5],
    )
    operation_monetization = OperationMonetization(
        gtm_profiles=gtm_profiles,
        monetization_patterns=monetization[:8],
        aarrr_notes={
            "Acquisition": [gtm_profiles[name] for name in names[:5] if name in gtm_profiles],
            "Activation": common_features[:5],
            "Retention": strengths[:5],
            "Revenue": monetization[:5],
            "Referral": opportunities[:5],
        },
    )
    purpose_sections = {
        "pm_report": {
            "market_background": market_background.model_dump(mode="json"),
            "feature_insights": feature_insights.model_dump(mode="json"),
            "operation_monetization": operation_monetization.model_dump(mode="json"),
        }
    }
    return market_background, feature_insights, operation_monetization, purpose_sections


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


def _clean_report_title(
    title: str,
    analysis_purpose: str,
    knowledge: list[CompetitorKnowledge],
    output_language: str,
) -> str:
    raw = " ".join((title or "").split())
    polluted = (
        "<parameter" in raw
        or "</parameter" in raw
        or '"executive_summary"' in raw
        or len(raw) > 120
    )
    if raw and not polluted:
        return raw
    names = "、".join(ck.competitor_name for ck in knowledge if ck.competitor_name)
    if output_language == "zh":
        purpose_label = {
            "choose_product": "选型分析",
            "build_product": "产品机会分析",
            "understand_industry": "行业分析",
            "analyze_growth_ops": "增长与商业化分析",
        }.get(analysis_purpose, "竞品分析")
        return f"{names} {purpose_label}" if names else "竞品分析报告"
    purpose_label = {
        "choose_product": "Product Selection Analysis",
        "build_product": "Product Opportunity Analysis",
        "understand_industry": "Industry Analysis",
        "analyze_growth_ops": "Growth and Monetization Analysis",
    }.get(analysis_purpose, "Competitive Analysis")
    return f"{names} {purpose_label}" if names else "Competitive Analysis Report"


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
    report.title = _clean_report_title(
        report.title,
        analysis_purpose,
        competitor_knowledge,
        output_language,
    )
    report.analysis_objective = _clean_function_call_artifacts(report.analysis_objective)
    report.analysis_frameworks = analysis_frameworks or ["swot"]
    report.selected_report_tabs = _selected_report_tabs(goals, report.analysis_frameworks, custom_dimensions)
    purpose_tab = {
        "choose_product": "scoring",
        "build_product": "opportunity",
        "understand_industry": "pm_sections",
        "analyze_growth_ops": "pm_sections",
    }.get(analysis_purpose)
    if purpose_tab and purpose_tab not in report.selected_report_tabs:
        insert_at = report.selected_report_tabs.index("recommendations") if "recommendations" in report.selected_report_tabs else len(report.selected_report_tabs)
        report.selected_report_tabs.insert(insert_at, purpose_tab)
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
    generated_custom_analysis = _build_custom_dimension_analysis(
        competitor_knowledge,
        custom_dimensions,
        output_language,
    )
    report.custom_dimension_analysis = {
        **generated_custom_analysis,
        **(report.custom_dimension_analysis or {}),
    }
    if analysis_purpose == "choose_product":
        generated_scores, generated_purpose = _build_choose_product_scores(
            competitor_knowledge,
            custom_dimensions=custom_dimensions,
        )
        report.competitor_scores = {
            **(report.competitor_scores or {}),
            **generated_scores,
        }
        report.purpose_sections = {
            **(report.purpose_sections or {}),
            **generated_purpose,
        }
        report.opportunity_score = None
        report.market_background = None
        report.feature_insights = None
        report.operation_monetization = None
    elif analysis_purpose == "build_product":
        generated_opportunity, generated_purpose = _build_product_opportunity(
            competitor_knowledge,
            output_language,
        )
        report.opportunity_score = report.opportunity_score or generated_opportunity
        report.purpose_sections = {
            **generated_purpose,
            **(report.purpose_sections or {}),
        }
        report.competitor_scores = {}
        report.market_background = None
        report.feature_insights = None
        report.operation_monetization = None
    elif analysis_purpose in {"understand_industry", "analyze_growth_ops"}:
        market_background, feature_insights, operation_monetization, generated_purpose = _build_pm_sections(
            competitor_knowledge,
            analysis_purpose,
            output_language,
        )
        report.market_background = report.market_background or market_background
        report.feature_insights = report.feature_insights or feature_insights
        report.operation_monetization = report.operation_monetization or operation_monetization
        report.purpose_sections = {
            **generated_purpose,
            **(report.purpose_sections or {}),
        }
        report.competitor_scores = {}
        report.opportunity_score = None
    else:
        report.competitor_scores = {}
        report.opportunity_score = None
        report.market_background = None
        report.feature_insights = None
        report.operation_monetization = None

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
