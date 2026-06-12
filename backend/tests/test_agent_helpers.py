"""Prompt loader and serialization helper unit tests.

These tests do not require LLM access. They exercise the pure helper
functions in :mod:`app.agents.analyst_agent` and :mod:`app.agents.writer_agent`
so we get coverage without making network calls.
"""

from app.agents import analyst_agent, writer_agent
from app.schemas.claim import Claim
from app.schemas.knowledge import (
    CompetitorKnowledge,
    ProductProfile,
)
from app.schemas.source import Reliability, SourceEvidence, SourceType


def _src(source_id: str, name: str = "Cursor") -> SourceEvidence:
    return SourceEvidence(
        source_id=source_id,
        competitor_name=name,
        source_type=SourceType.pricing_page,
        url="https://cursor.com/pricing",
        title="Pricing",
        snippet="snippet text",
        content="long content " * 200,
        reliability=Reliability.high,
    )


def test_analyst_prompt_loads_non_empty():
    text = analyst_agent._load_prompt()
    assert "AnalystAgent" in text
    assert "RawCompetitorExtraction" in text


def test_writer_prompt_loads_non_empty():
    text = writer_agent._load_prompt()
    assert "WriterAgent" in text
    assert "CompetitiveReport" in text


def test_analyst_groups_sources_by_competitor():
    sources = [
        _src("src_a", "Cursor"),
        _src("src_b", "Trae"),
        _src("src_c", "Cursor"),
    ]
    grouped = analyst_agent._group_sources_by_competitor(sources)
    assert set(grouped.keys()) == {"Cursor", "Trae"}
    assert [s.source_id for s in grouped["Cursor"]] == ["src_a", "src_c"]


def test_analyst_build_user_message_includes_source_id_and_truncates_content():
    sources = [_src("src_abc")]
    msg = analyst_agent._build_user_message(
        competitor_name="Cursor",
        sources=sources,
        goals=["pricing_analysis"],
        rework_hints=None,
    )
    assert "[src_abc]" in msg
    assert "Cursor" in msg
    assert "pricing_analysis" in msg
    # Long content should have been truncated to <= 2000 chars (plus header).
    # Check the message length is reasonable, not megabytes.
    assert len(msg) < 6000


def test_analyst_build_user_message_renders_rework_hints():
    sources = [_src("src_abc")]
    msg = analyst_agent._build_user_message(
        competitor_name="Cursor",
        sources=sources,
        goals=[],
        rework_hints=["Collect pricing page", "Add positioning claim"],
    )
    assert "Collect pricing page" in msg
    assert "Add positioning claim" in msg
    assert "Previous QA feedback" in msg


def test_analyst_parse_raw_extraction_backfills_name():
    import json
    content = json.dumps({"positioning": "AI IDE"})  # missing "name"
    result = analyst_agent._parse_raw_extraction(content, "Cursor")
    assert result is not None
    assert result.name == "Cursor"


def test_writer_serialize_knowledge_truncates_long_payloads():
    knowledge = CompetitorKnowledge(
        competitor_id="comp_1",
        competitor_name="Cursor",
        product_profile=ProductProfile(
            name="Cursor",
            website="https://cursor.com",
            positioning=Claim(text="x" * 10000),
        ),
    )
    rendered = writer_agent._serialize_knowledge([knowledge])
    assert "Cursor" in rendered
    assert "x" * 10000 in rendered
    assert "...(truncated)" not in rendered


def test_writer_render_source_index_lists_all_sources():
    sources = [_src("src_a"), _src("src_b")]
    rendered = writer_agent._render_source_index(sources)
    assert "src_a" in rendered
    assert "src_b" in rendered
    assert "pricing_page" in rendered


def test_writer_bind_report_fields_overwrites_project_and_source_list():
    from app.schemas.report import CompetitiveReport

    report = CompetitiveReport(project_id="wrong_project")
    knowledge = [CompetitorKnowledge(competitor_id="comp_1", competitor_name="Cursor")]
    sources = [_src("src_a")]

    bound = writer_agent._bind_report_fields(
        report,
        project_id="proj_1",
        competitor_knowledge=knowledge,
        sources=sources,
    )
    assert bound.project_id == "proj_1"
    assert [s.source_id for s in bound.source_list] == ["src_a"]
    # Competitor overview was empty; the writer backfilled it.
    assert [ck.competitor_name for ck in bound.competitor_overview] == ["Cursor"]
