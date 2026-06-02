"""Deterministic markdown renderer tests.

Tests verify that render_report_markdown produces stable, language-correct
output using only real source_ids from the provided sources list.

All tests operate on pure Pydantic objects — no DB, LLM, or network access.
"""

import re

import pytest

from app.agents.writer_agent import _bind_report_fields
from app.schemas.claim import Claim
from app.schemas.knowledge import (
    CompetitorKnowledge,
    FeatureCategory,
    FeatureItem,
    PricingModel,
    PricingPlan,
    SWOTAnalysis,
)
from app.schemas.report import CompetitiveReport
from app.schemas.source import Reliability, SourceEvidence, SourceType
from app.services.markdown_renderer import render_report_markdown


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_source(source_id: str, competitor_name: str = "Cursor") -> SourceEvidence:
    return SourceEvidence(
        source_id=source_id,
        competitor_name=competitor_name,
        source_type=SourceType.official_website,
        url=f"https://cursor.so/{source_id}",
        title=f"{source_id} page title",
        reliability=Reliability.high,
    )


def _make_knowledge(source_id: str) -> CompetitorKnowledge:
    return CompetitorKnowledge(
        competitor_id="comp_1",
        competitor_name="Cursor",
        pricing_model=PricingModel(
            has_free_plan=False,
            plans=[PricingPlan(name="Pro", price="$20", billing_cycle="monthly")],
        ),
        feature_tree=[
            FeatureCategory(
                category="AI",
                features=[
                    FeatureItem(
                        name="Autocomplete",
                        availability="available",
                        evidence=[source_id],
                    )
                ],
            )
        ],
        swot=SWOTAnalysis(
            strengths=[Claim(text="Fast AI completions", evidence=[source_id])],
            weaknesses=[Claim(text="Expensive Pro tier", evidence=[source_id])],
        ),
    )


def _make_report(
    sources: list[SourceEvidence],
    knowledge: list[CompetitorKnowledge],
) -> CompetitiveReport:
    sid = sources[0].source_id if sources else "src_fallback000"
    return CompetitiveReport(
        project_id="proj_test",
        title="Competitive Analysis: AI IDE Tools",
        executive_summary=[Claim(text="Cursor is the market leader", evidence=[sid])],
        strategic_recommendations=[Claim(text="Invest in AI features", evidence=[sid])],
        competitor_overview=knowledge,
        source_list=sources,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_markdown_renderer_citations_are_stable():
    """Same structured input must produce identical markdown on every call."""
    src = _make_source("src_abc123def456")
    knowledge = _make_knowledge(src.source_id)
    report = _make_report([src], [knowledge])

    md1 = render_report_markdown(report, [src], output_language="en")
    md2 = render_report_markdown(report, [src], output_language="en")

    assert md1 == md2, "render_report_markdown is not deterministic"

    # Every inline citation must be a real source_id from the provided list
    valid_ids = {src.source_id}
    inline_ids = set(re.findall(r"\[\^(src_[0-9a-f]+)\]", md1))
    unknown = inline_ids - valid_ids
    assert not unknown, f"Inline citations reference unknown source_ids: {unknown}"


def test_markdown_renderer_zh_headings():
    """output_language='zh' must produce Chinese section headings."""
    src = _make_source("src_abc123def456")
    knowledge = _make_knowledge(src.source_id)
    report = _make_report([src], [knowledge])

    md = render_report_markdown(report, [src], output_language="zh")

    assert "## 执行摘要" in md
    assert "## 定价对比" in md
    assert "## SWOT 分析" in md
    assert "## 战略建议" in md
    assert "## 数据来源" in md
    # English headings must not appear
    assert "## Executive Summary" not in md
    assert "## Pricing Comparison" not in md
    assert "## Sources" not in md


def test_output_language_zh_reaches_writer_agent():
    """_bind_report_fields must propagate output_language to the renderer."""
    src = _make_source("src_abc123def456")
    knowledge = _make_knowledge(src.source_id)
    report = _make_report([src], [knowledge])

    result = _bind_report_fields(
        report,
        project_id="proj_test",
        competitor_knowledge=[knowledge],
        sources=[src],
        output_language="zh",
    )

    assert "## 执行摘要" in result.markdown_content
    assert "## 定价对比" in result.markdown_content
    assert "## 数据来源" in result.markdown_content


def test_markdown_sources_section_contains_all_used_sources():
    """Every source_id cited in a claim must appear as a footnote definition."""
    src = _make_source("src_abc123def456")
    knowledge = _make_knowledge(src.source_id)
    report = _make_report([src], [knowledge])

    md = render_report_markdown(report, [src], output_language="en")

    # Collect all inline citation ids
    inline_ids = set(re.findall(r"\[\^(src_[0-9a-f]+)\]", md))
    assert src.source_id in inline_ids, "Source used in claims must appear inline"

    # Collect all footnote definition ids
    definition_ids = set(re.findall(r"^\[\^(src_[0-9a-f]+)\]:", md, re.MULTILINE))
    missing = inline_ids - definition_ids
    assert not missing, (
        f"Inline citations without footnote definitions: {missing}"
    )
    # The source URL must appear in the footnotes
    assert src.url in md


def test_markdown_does_not_use_llm_freeform_citation_format():
    """Rendered markdown must only use [^src_xxx] — never raw [src_xxx]."""
    src = _make_source("src_abc123def456")
    knowledge = _make_knowledge(src.source_id)
    report = _make_report([src], [knowledge])

    md = render_report_markdown(report, [src], output_language="en")

    # Old format: [src_xxx] without the ^ — must not appear
    old_format = re.findall(r"(?<!\^)\[src_[0-9a-f]+\]", md)
    assert not old_format, (
        f"Old LLM citation format found in rendered markdown: {old_format}"
    )
    # New format: [^src_xxx] — must appear (at least inline or as definition)
    new_format = re.findall(r"\[\^src_[0-9a-f]+\]", md)
    assert new_format, "No [^src_xxx] citations found in rendered markdown"
