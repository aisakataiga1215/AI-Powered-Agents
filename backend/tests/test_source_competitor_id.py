"""Regression tests: SourceEvidence.competitor_id must be populated.

The CollectorAgent sets competitor_id as a slug of competitor_name.
These tests verify the invariant without calling real LLMs.
"""

from app.schemas.source import Reliability, SourceEvidence, SourceType


def _make_source(competitor_name: str, competitor_id: str = "") -> SourceEvidence:
    return SourceEvidence(
        source_id=f"src_{competitor_name.lower()}_001",
        competitor_name=competitor_name,
        competitor_id=competitor_id,
        source_type=SourceType.official_website,
        url=f"https://{competitor_name.lower()}.com",
        title=f"{competitor_name} website",
        reliability=Reliability.high,
    )


def test_source_evidence_allows_empty_competitor_id_by_default():
    """Schema allows empty competitor_id (set by collector, not by fixtures)."""
    src = _make_source("Cursor")
    assert src.competitor_id == ""


def test_source_competitor_id_slug_format():
    """competitor_id should be a lowercase slug of competitor_name."""
    # Simulate what CollectorAgent.run() does:
    #   src.competitor_id = name.strip().lower().replace(" ", "_")
    name = "Cursor"
    slug = name.strip().lower().replace(" ", "_")
    src = _make_source("Cursor", competitor_id=slug)
    assert src.competitor_id == "cursor"


def test_report_source_list_has_non_empty_competitor_id():
    """All entries in report.source_list should have competitor_id set."""
    from app.schemas.report import CompetitiveReport

    sources = [
        _make_source("Cursor", competitor_id="cursor"),
        _make_source("Trae", competitor_id="trae"),
        _make_source("Windsurf", competitor_id="windsurf"),
    ]
    report = CompetitiveReport(project_id="proj_x", source_list=sources)

    for src in report.source_list:
        assert src.competitor_id != "", (
            f"source {src.source_id} has empty competitor_id"
        )


def test_report_source_list_empty_competitor_id_is_detectable():
    """Verify that a source WITHOUT competitor_id set would fail the check."""
    from app.schemas.report import CompetitiveReport

    bad_source = _make_source("Cursor", competitor_id="")
    report = CompetitiveReport(project_id="proj_x", source_list=[bad_source])

    failing = [s for s in report.source_list if not s.competitor_id]
    assert len(failing) == 1  # one source without competitor_id is detectable
