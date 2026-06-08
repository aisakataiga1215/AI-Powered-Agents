"""Deterministic markdown renderer for competitive analysis reports.

Replaces raw ``[src_xxx]`` tokens emitted by the LLM with numbered
citations ``[N]`` whose order matches first-appearance in the rendered
report body.  Appends a canonical References section so every citation
resolves to a human-readable source line.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.schemas.report import CompetitiveReport
    from app.schemas.source import SourceEvidence

# Matches: [src_abc], [src_abc, src_def], (src_abc)
_SINGLE_RE = re.compile(r"\[src_[0-9a-f]+\]")
_MULTI_RE = re.compile(r"\[(?:src_[0-9a-f]+)(?:,\s*src_[0-9a-f]+)+\]")
_PAREN_RE = re.compile(r"\(src_([0-9a-f]+)\)")
# Trailing references/sources section to strip before appending a new one
_REFS_SECTION_RE = re.compile(
    r"\n## (?:References|Sources|参考资料|来源).*$", re.DOTALL | re.IGNORECASE
)


def build_citation_index(report: "CompetitiveReport") -> dict[str, int]:
    """Return a mapping of source_id → citation number (1-based).

    Numbers are assigned in the order each source_id first appears
    when traversing the report in standard render order:
      1. executive_summary
      2. competitor_overview (positioning → target_users → user_personas → swot)
      3. strategic_recommendations
    """
    seen: list[str] = []

    def _see(source_id: str) -> None:
        if source_id not in seen:
            seen.append(source_id)

    for claim in report.executive_summary or []:
        for sid in claim.evidence or []:
            _see(sid)

    for comp in report.competitor_overview or []:
        pp = comp.product_profile
        if pp:
            for sid in (pp.positioning.evidence if pp.positioning else []) or []:
                _see(sid)
            for claim in pp.target_users or []:
                for sid in claim.evidence or []:
                    _see(sid)
        for persona in comp.user_personas or []:
            for sid in persona.evidence or []:
                _see(sid)
        swot = comp.swot
        if swot:
            for quadrant in (swot.strengths, swot.weaknesses, swot.opportunities, swot.threats):
                for claim in quadrant or []:
                    for sid in claim.evidence or []:
                        _see(sid)

    for claim in report.strategic_recommendations or []:
        for sid in claim.evidence or []:
            _see(sid)

    return {sid: i + 1 for i, sid in enumerate(seen)}


def clean_citations(text: str, citation_index: dict[str, int]) -> str:
    """Replace raw source-ID patterns in *text* with ``[N]`` superscripts."""

    def _replace_multi(m: re.Match) -> str:
        inner = m.group(0)[1:-1]  # strip outer [ ]
        ids = [p.strip() for p in inner.split(",")]
        nums = []
        for raw_id in ids:
            sid = raw_id if raw_id.startswith("src_") else f"src_{raw_id}"
            n = citation_index.get(sid)
            if n is not None:
                nums.append(f"[{n}]")
        return "".join(nums) if nums else m.group(0)

    def _replace_single(m: re.Match) -> str:
        sid = m.group(0)[1:-1]  # strip [ ]
        n = citation_index.get(sid)
        return f"[{n}]" if n is not None else m.group(0)

    def _replace_paren(m: re.Match) -> str:
        sid = f"src_{m.group(1)}"
        n = citation_index.get(sid)
        return f"[{n}]" if n is not None else m.group(0)

    # Process multi-source brackets first to avoid partial matches
    text = _MULTI_RE.sub(_replace_multi, text)
    text = _SINGLE_RE.sub(_replace_single, text)
    text = _PAREN_RE.sub(_replace_paren, text)
    return text


def _strip_references_section(text: str) -> str:
    return _REFS_SECTION_RE.sub("", text)


def build_references_section(
    citation_index: dict[str, int],
    source_list: "list[SourceEvidence]",
) -> str:
    """Return a markdown References section with numbered entries."""
    if not citation_index and not source_list:
        return ""

    source_map = {s.source_id: s for s in source_list}

    used_ids = sorted(citation_index, key=lambda sid: citation_index[sid])
    unused_ids = [s.source_id for s in source_list if s.source_id not in citation_index]

    lines: list[str] = ["## References", ""]
    for sid in used_ids:
        n = citation_index[sid]
        src = source_map.get(sid)
        if src:
            lines.append(f"[{n}] {src.title} — {src.url}  ")
            lines.append(f"    Source ID: {sid}")
        else:
            lines.append(f"[{n}] Source ID: {sid}")
        lines.append("")

    if unused_ids:
        lines.append("### Additional Sources")
        lines.append("")
        for sid in unused_ids:
            src = source_map.get(sid)
            if src:
                lines.append(f"- {src.title} — {src.url}  ")
                lines.append(f"  Source ID: {sid}")
            else:
                lines.append(f"- Source ID: {sid}")
        lines.append("")

    return "\n".join(lines)


def render_report_markdown(report: "CompetitiveReport") -> str:
    """Return cleaned markdown_content with deterministic ``[N]`` citations.

    1. Builds first-appearance citation index from structured claims.
    2. Strips any existing References/Sources section from the LLM text.
    3. Replaces all raw ``[src_xxx]`` / ``(src_xxx)`` patterns with ``[N]``.
    4. Appends a canonical References section.
    """
    citation_index = build_citation_index(report)
    text = _strip_references_section(report.markdown_content or "")
    text = clean_citations(text, citation_index)
    refs = build_references_section(citation_index, report.source_list or [])
    if refs:
        text = text.rstrip() + "\n\n" + refs
    return text
