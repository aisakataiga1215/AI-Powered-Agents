"""Tests for the deterministic markdown renderer."""

from __future__ import annotations

import pytest

from app.schemas.claim import Claim
from app.schemas.knowledge import CompetitorKnowledge, ProductProfile, SWOTAnalysis
from app.schemas.report import CompetitiveReport
from app.schemas.source import SourceEvidence, SourceType, Reliability
from app.services.markdown_renderer import (
    build_citation_index,
    build_references_section,
    clean_citations,
    render_report_markdown,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _source(source_id: str, title: str = "Test Source", url: str = "https://example.com") -> SourceEvidence:
    return SourceEvidence(
        source_id=source_id,
        competitor_name="TestCo",
        source_type=SourceType.official_website,
        url=url,
        title=title,
    )


def _claim(text: str, evidence: list[str] | None = None) -> Claim:
    return Claim(text=text, evidence=evidence or [])


def _minimal_report(
    executive_summary: list[Claim] | None = None,
    strategic_recommendations: list[Claim] | None = None,
    source_list: list[SourceEvidence] | None = None,
    markdown_content: str = "",
) -> CompetitiveReport:
    return CompetitiveReport(
        executive_summary=executive_summary or [],
        competitor_overview=[],
        strategic_recommendations=strategic_recommendations or [],
        source_list=source_list or [],
        markdown_content=markdown_content,
    )


# ---------------------------------------------------------------------------
# build_citation_index
# ---------------------------------------------------------------------------

class TestBuildCitationIndex:
    def test_empty_report_returns_empty_index(self):
        report = _minimal_report()
        assert build_citation_index(report) == {}

    def test_assigns_numbers_in_first_appearance_order(self):
        report = _minimal_report(
            executive_summary=[
                _claim("first", ["src_aaa"]),
                _claim("second", ["src_bbb"]),
            ]
        )
        idx = build_citation_index(report)
        assert idx["src_aaa"] == 1
        assert idx["src_bbb"] == 2

    def test_deduplicates_repeated_source_ids(self):
        report = _minimal_report(
            executive_summary=[
                _claim("a", ["src_aaa"]),
                _claim("b", ["src_aaa", "src_bbb"]),
            ]
        )
        idx = build_citation_index(report)
        assert idx == {"src_aaa": 1, "src_bbb": 2}

    def test_executive_summary_before_strategic_recommendations(self):
        report = _minimal_report(
            executive_summary=[_claim("exec", ["src_exec"])],
            strategic_recommendations=[_claim("strat", ["src_strat"])],
        )
        idx = build_citation_index(report)
        assert idx["src_exec"] == 1
        assert idx["src_strat"] == 2

    def test_competitor_overview_sources_numbered_after_executive_summary(self):
        comp = CompetitorKnowledge(
            competitor_id="c1",
            competitor_name="Acme",
            product_profile=ProductProfile(
                name="Acme Product",
                website="https://acme.com",
                positioning=_claim("leader", ["src_pos"]),
            ),
        )
        report = CompetitiveReport(
            executive_summary=[_claim("exec", ["src_exec"])],
            competitor_overview=[comp],
            strategic_recommendations=[],
            source_list=[],
            markdown_content="",
        )
        idx = build_citation_index(report)
        assert idx["src_exec"] == 1
        assert idx["src_pos"] == 2

    def test_swot_sources_are_indexed(self):
        comp = CompetitorKnowledge(
            competitor_id="c1",
            competitor_name="Acme",
            swot=SWOTAnalysis(
                strengths=[_claim("s", ["src_str"])],
                weaknesses=[_claim("w", ["src_weak"])],
            ),
        )
        report = CompetitiveReport(
            executive_summary=[],
            competitor_overview=[comp],
            strategic_recommendations=[],
            source_list=[],
            markdown_content="",
        )
        idx = build_citation_index(report)
        assert idx["src_str"] == 1
        assert idx["src_weak"] == 2


# ---------------------------------------------------------------------------
# clean_citations
# ---------------------------------------------------------------------------

class TestCleanCitations:
    def setup_method(self):
        self.index = {"src_aaa": 1, "src_bbb": 2, "src_ccc": 3}

    def test_replaces_single_bracket(self):
        result = clean_citations("See [src_aaa] for details.", self.index)
        assert result == "See [1] for details."

    def test_replaces_multi_source_bracket(self):
        result = clean_citations("Claims [src_aaa, src_bbb].", self.index)
        assert result == "Claims [1][2]."

    def test_replaces_parenthesized_pattern(self):
        result = clean_citations("Evidence (src_aaa).", self.index)
        assert result == "Evidence [1]."

    def test_unknown_source_id_preserved(self):
        result = clean_citations("See [src_zzz].", self.index)
        assert result == "See [src_zzz]."

    def test_multiple_replacements_in_same_line(self):
        result = clean_citations("[src_aaa] and [src_bbb] confirm [src_ccc].", self.index)
        assert result == "[1] and [2] confirm [3]."

    def test_no_raw_src_in_output(self):
        text = "A [src_aaa] B [src_bbb] C [src_aaa, src_ccc] D (src_bbb)"
        result = clean_citations(text, self.index)
        assert "src_" not in result

    def test_multi_source_with_spaces(self):
        result = clean_citations("See [src_aaa,  src_bbb].", self.index)
        assert result == "See [1][2]."


# ---------------------------------------------------------------------------
# build_references_section
# ---------------------------------------------------------------------------

class TestBuildReferencesSection:
    def test_empty_inputs_return_empty_string(self):
        assert build_references_section({}, []) == ""

    def test_lists_used_sources_in_number_order(self):
        idx = {"src_b": 2, "src_a": 1}
        sources = [
            _source("src_a", "Title A", "https://a.com"),
            _source("src_b", "Title B", "https://b.com"),
        ]
        section = build_references_section(idx, sources)
        lines = section.splitlines()
        assert lines[0] == "## References"
        assert any("[1]" in l and "Title A" in l for l in lines)
        assert any("[2]" in l and "Title B" in l for l in lines)
        # [1] must appear before [2]
        idx_1 = next(i for i, l in enumerate(lines) if "[1]" in l)
        idx_2 = next(i for i, l in enumerate(lines) if "[2]" in l)
        assert idx_1 < idx_2

    def test_source_id_line_present(self):
        idx = {"src_abc123": 1}
        sources = [_source("src_abc123", "My Source")]
        section = build_references_section(idx, sources)
        assert "Source ID: src_abc123" in section

    def test_unused_sources_in_additional_section(self):
        idx = {"src_used": 1}
        sources = [
            _source("src_used", "Used"),
            _source("src_unused", "Unused"),
        ]
        section = build_references_section(idx, sources)
        assert "Additional Sources" in section
        assert "src_unused" in section

    def test_no_additional_section_when_all_sources_cited(self):
        idx = {"src_a": 1}
        sources = [_source("src_a")]
        section = build_references_section(idx, sources)
        assert "Additional Sources" not in section


# ---------------------------------------------------------------------------
# render_report_markdown
# ---------------------------------------------------------------------------

class TestRenderReportMarkdown:
    def test_replaces_raw_tokens_in_body(self):
        src = _source("src_abc", "Page A", "https://a.com")
        report = _minimal_report(
            executive_summary=[_claim("Point one", ["src_abc"])],
            source_list=[src],
            markdown_content="## Summary\n\nPoint one [src_abc].\n",
        )
        result = render_report_markdown(report)
        assert "[src_abc]" not in result
        assert "[1]" in result

    def test_appends_references_section(self):
        src = _source("src_abc", "Page A")
        report = _minimal_report(
            executive_summary=[_claim("x", ["src_abc"])],
            source_list=[src],
            markdown_content="body",
        )
        result = render_report_markdown(report)
        assert "## References" in result

    def test_strips_existing_references_section(self):
        src = _source("src_abc", "Page A")
        report = _minimal_report(
            executive_summary=[_claim("x", ["src_abc"])],
            source_list=[src],
            markdown_content="body\n\n## References\n\nold content",
        )
        result = render_report_markdown(report)
        assert result.count("## References") == 1

    def test_no_raw_src_in_final_body(self):
        sources = [_source(f"src_{c}", f"Title {c}") for c in ("aaa", "bbb", "ccc")]
        report = _minimal_report(
            executive_summary=[
                _claim("a", ["src_aaa"]),
                _claim("b", ["src_bbb"]),
                _claim("c", ["src_ccc"]),
            ],
            source_list=sources,
            markdown_content=(
                "## Summary\n\n"
                "Point A [src_aaa]. Point B [src_bbb, src_ccc]. Also (src_aaa).\n"
            ),
        )
        result = render_report_markdown(report)
        # Split off the References section; body must have no raw src_ tokens
        body = result.split("## References")[0]
        assert "src_" not in body

    def test_empty_report_produces_no_crash(self):
        report = _minimal_report()
        result = render_report_markdown(report)
        assert isinstance(result, str)

    def test_source_id_appears_in_references_not_body(self):
        src = _source("src_deadbeef1234", "Important Doc", "https://docs.example.com")
        report = _minimal_report(
            executive_summary=[_claim("Finding", ["src_deadbeef1234"])],
            source_list=[src],
            markdown_content="## Summary\n\nFinding [src_deadbeef1234].\n",
        )
        result = render_report_markdown(report)
        body = result.split("## References")[0]
        refs = result.split("## References")[1]
        assert "src_deadbeef1234" not in body
        assert "src_deadbeef1234" in refs
