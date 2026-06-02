"""Deterministic markdown renderer for CompetitiveReport.

Builds ``markdown_content`` from structured Pydantic fields — no LLM text
is used. Guarantees:

* Citations are always valid: only real source_ids appear as ``[^src_xxx]``.
* Language headings match ``output_language`` exactly.
* Output is stable across re-runs for identical structured input.

Citation format
---------------
Inline:    ``[^src_xxx]`` appended after claim text
Footnotes: ``[^src_xxx]: Title — URL`` in the Sources section
"""

from __future__ import annotations

from app.schemas.claim import Claim
from app.schemas.knowledge import CompetitorKnowledge
from app.schemas.report import CompetitiveReport
from app.schemas.source import SourceEvidence

_H_EN: dict[str, str] = {
    "executive_summary": "## Executive Summary",
    "feature_comparison": "## Feature Comparison",
    "pricing_comparison": "## Pricing Comparison",
    "swot": "## SWOT Analysis",
    "recommendations": "## Strategic Recommendations",
    "sources": "## Sources",
}

_H_ZH: dict[str, str] = {
    "executive_summary": "## 执行摘要",
    "feature_comparison": "## 功能对比",
    "pricing_comparison": "## 定价对比",
    "swot": "## SWOT 分析",
    "recommendations": "## 战略建议",
    "sources": "## 数据来源",
}

_AVAIL_ZH: dict[str, str] = {
    "available": "支持",
    "limited": "有限",
    "unknown": "未知",
}


def _h(lang: str) -> dict[str, str]:
    return _H_ZH if lang == "zh" else _H_EN


def _cite(evidence: list[str]) -> str:
    return "".join(f"[^{sid}]" for sid in evidence if sid)


def _render_claims(claims: list[Claim]) -> str:
    return "\n".join(f"- {c.text}{_cite(c.evidence)}" for c in claims)


def _feature_table(knowledge: list[CompetitorKnowledge], lang: str) -> str:
    comps = [ck for ck in knowledge if ck.competitor_name and ck.feature_tree]
    if not comps:
        return ""

    seen: set[tuple[str, str]] = set()
    ordered: list[tuple[str, str]] = []
    for ck in comps:
        for cat in ck.feature_tree:
            for f in cat.features:
                key = (cat.category, f.name)
                if key not in seen:
                    seen.add(key)
                    ordered.append(key)
    if not ordered:
        return ""

    avail_lookup: dict[tuple[str, str, str], str] = {}
    for ck in comps:
        for cat in ck.feature_tree:
            for f in cat.features:
                avail_lookup[(cat.category, f.name, ck.competitor_name)] = f.availability

    comp_names = [ck.competitor_name for ck in comps]
    feat_label = "功能" if lang == "zh" else "Feature"
    headers = [feat_label] + comp_names
    header_row = "| " + " | ".join(headers) + " |"
    sep_row = "|" + "---|" * len(headers)

    rows: list[str] = []
    for cat, feat_name in ordered:
        label = f"{feat_name} ({cat})"
        cells: list[str] = []
        for comp in comp_names:
            raw = avail_lookup.get((cat, feat_name, comp), "—")
            if lang == "zh":
                raw = _AVAIL_ZH.get(raw, raw)
            cells.append(raw)
        rows.append("| " + " | ".join([label] + cells) + " |")

    return header_row + "\n" + sep_row + "\n" + "\n".join(rows)


def _pricing_table(knowledge: list[CompetitorKnowledge], lang: str) -> str:
    rows: list[tuple[str, str, str, str]] = []
    for ck in knowledge:
        if not ck.pricing_model or not ck.pricing_model.plans:
            continue
        for plan in ck.pricing_model.plans:
            price = plan.price.strip()
            billing = plan.billing_cycle.strip()
            price_str = price if price.lower() == "free" else f"{price}/{billing}"
            rows.append((ck.competitor_name, plan.name, price_str, billing))
    if not rows:
        return ""

    if lang == "zh":
        header = "| 竞品 | 方案 | 价格 | 计费周期 |\n|---|---|---|---|"
    else:
        header = "| Competitor | Plan | Price | Billing |\n|---|---|---|---|"
    data = "\n".join(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |" for r in rows)
    return header + "\n" + data


def _swot_section(knowledge: list[CompetitorKnowledge], lang: str) -> str:
    if lang == "zh":
        labels = {
            "strengths": "优势",
            "weaknesses": "劣势",
            "opportunities": "机遇",
            "threats": "威胁",
        }
    else:
        labels = {
            "strengths": "Strengths",
            "weaknesses": "Weaknesses",
            "opportunities": "Opportunities",
            "threats": "Threats",
        }

    blocks: list[str] = []
    for ck in knowledge:
        if not ck.swot:
            continue
        parts: list[str] = [f"### {ck.competitor_name}"]
        for key, label in labels.items():
            claims: list[Claim] = getattr(ck.swot, key, [])
            if claims:
                parts.append(f"**{label}**")
                for c in claims:
                    parts.append(f"- {c.text}{_cite(c.evidence)}")
        if len(parts) > 1:
            blocks.append("\n".join(parts))
    return "\n\n".join(blocks)


def _collect_cited_ids(
    report: CompetitiveReport,
    knowledge: list[CompetitorKnowledge],
) -> list[str]:
    """Return all cited source_ids in stable first-seen order."""
    seen: set[str] = set()
    ordered: list[str] = []

    def _add(ids: list[str]) -> None:
        for sid in ids:
            if sid and sid not in seen:
                seen.add(sid)
                ordered.append(sid)

    for c in report.executive_summary:
        _add(c.evidence)
    for ck in knowledge:
        if not ck.swot:
            continue
        for claims in (
            ck.swot.strengths,
            ck.swot.weaknesses,
            ck.swot.opportunities,
            ck.swot.threats,
        ):
            for c in claims:
                _add(c.evidence)
    for c in report.strategic_recommendations:
        _add(c.evidence)

    return ordered


def render_report_markdown(
    report: CompetitiveReport,
    sources: list[SourceEvidence],
    output_language: str = "en",
) -> str:
    """Build full deterministic markdown from structured report fields.

    All inline citations are ``[^src_xxx]`` markers referencing real
    source_ids from ``sources``. A ``## Sources`` (or ``## 数据来源``)
    section at the end defines each footnote as ``[^src_xxx]: Title — URL``.
    """
    lang = output_language if output_language in ("en", "zh") else "en"
    h = _h(lang)
    knowledge = report.competitor_overview
    source_map: dict[str, SourceEvidence] = {s.source_id: s for s in sources}

    parts: list[str] = [f"# {report.title}"]

    if report.executive_summary:
        parts.append(h["executive_summary"])
        parts.append(_render_claims(report.executive_summary))

    feat_md = _feature_table(knowledge, lang)
    if feat_md:
        parts.append(h["feature_comparison"])
        parts.append(feat_md)

    pricing_md = _pricing_table(knowledge, lang)
    if pricing_md:
        parts.append(h["pricing_comparison"])
        parts.append(pricing_md)

    swot_md = _swot_section(knowledge, lang)
    if swot_md:
        parts.append(h["swot"])
        parts.append(swot_md)

    if report.strategic_recommendations:
        parts.append(h["recommendations"])
        parts.append(_render_claims(report.strategic_recommendations))

    cited = _collect_cited_ids(report, knowledge)
    footnotes: list[str] = []
    for sid in cited:
        src = source_map.get(sid)
        if src:
            title = src.title or sid
            footnotes.append(f"[^{sid}]: {title} — {src.url}")

    if footnotes:
        parts.append(h["sources"])
        parts.append("\n".join(footnotes))

    return "\n\n".join(parts)
