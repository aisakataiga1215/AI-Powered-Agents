"""CollectorAgent integration tests.

Exercises the collector against the demo fixture loader. No network or
LLM access. Uses an in-memory SQLite engine so each test is isolated.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents import collector_agent
from app.core.config import settings
from app.db import models
from app.schemas.source import SourceType


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    models.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = session_factory()
    project = models.Project(
        id="proj_test",
        industry="AI Coding",
        goals="[]",
        status="created",
        output_language="en",
        report_depth="standard",
    )
    session.add(project)
    session.commit()
    try:
        yield session
    finally:
        session.close()


def test_collector_loads_demo_fixtures(db_session):
    sources = collector_agent.run(
        db=db_session,
        project_id="proj_test",
        competitors=[{"name": "Cursor", "url": "https://cursor.com"}],
        goals=["pricing_analysis"],
    )
    assert len(sources) > 0
    # Every loaded source must be bound to the active project so QA can
    # cross-reference it later.
    assert all(s.project_id == "proj_test" for s in sources)
    assert all(s.competitor_name == "Cursor" for s in sources)


def test_collector_handles_unknown_competitor(db_session):
    # Unknown competitors should not raise; we simply log and return
    # whatever we could load (empty list in this case).
    sources = collector_agent.run(
        db=db_session,
        project_id="proj_test",
        competitors=[{"name": "DoesNotExist", "url": "https://example.com"}],
        goals=[],
    )
    assert sources == []


def test_collector_skips_competitor_without_name(db_session):
    sources = collector_agent.run(
        db=db_session,
        project_id="proj_test",
        competitors=[{"url": "https://example.com"}],
        goals=[],
    )
    assert sources == []


def test_collector_records_agent_run(db_session):
    collector_agent.run(
        db=db_session,
        project_id="proj_test",
        competitors=[{"name": "Cursor", "url": "https://cursor.com"}],
        goals=[],
    )
    runs = (
        db_session.query(models.AgentRun)
        .filter(models.AgentRun.project_id == "proj_test")
        .all()
    )
    assert len(runs) == 1
    assert runs[0].agent_name == "CollectorAgent"
    assert runs[0].status == "success"


def test_collector_converts_research_inputs_to_manual_sources(db_session):
    sources = collector_agent.run(
        db=db_session,
        project_id="proj_test",
        competitors=[{"name": "Cursor", "url": "https://cursor.com"}],
        goals=["user_personas"],
        research_inputs=[
            {
                "title": "Interview notes",
                "source_kind": "interview",
                "competitor_name": "Cursor",
                "content": "Developers like Cursor for repository-wide context.",
            }
        ],
    )
    manual_sources = [s for s in sources if s.source_type is SourceType.manual_input]
    assert len(manual_sources) == 1
    assert manual_sources[0].competitor_name == "Cursor"
    assert manual_sources[0].data_source == "manual"
    assert "repository-wide context" in manual_sources[0].content

    run_row = (
        db_session.query(models.AgentRun)
        .filter(models.AgentRun.project_id == "proj_test")
        .order_by(models.AgentRun.created_at.desc())
        .first()
    )
    assert '"manual_source_count": 1' in (run_row.output_json or "")


def test_collector_applies_global_research_input_to_each_competitor(db_session):
    sources = collector_agent.run(
        db=db_session,
        project_id="proj_test",
        competitors=[
            {"name": "Cursor", "url": "https://cursor.com"},
            {"name": "Trae", "url": "https://www.trae.ai"},
        ],
        goals=["user_personas"],
        research_inputs=[
            {
                "title": "Survey summary",
                "source_kind": "survey",
                "content": "Respondents want clearer pricing and privacy controls.",
            }
        ],
    )
    manual_competitors = {
        s.competitor_name for s in sources if s.source_type is SourceType.manual_input
    }
    assert manual_competitors == {"Cursor", "Trae"}


def test_collector_sanitizes_all_research_input_kinds(db_session):
    sources = collector_agent.run(
        db=db_session,
        project_id="proj_test",
        competitors=[{"name": "Cursor", "url": "https://cursor.com"}],
        goals=["user_personas"],
        research_inputs=[
            {
                "title": "Desk research notes",
                "source_kind": "desk_research",
                "competitor_name": "Cursor",
                "content": "回访电话 138 1234 5678,用户希望改进团队权限。",
            },
            {
                "title": "Internal note",
                "source_kind": "notes",
                "competitor_name": "Cursor",
                "content": "Contact alice@example.com,反馈是希望增强导出能力。",
            },
        ],
    )
    manual_sources = [s for s in sources if s.source_type is SourceType.manual_input]
    assert len(manual_sources) == 2
    assert all(s.desensitized for s in manual_sources)
    assert all(s.contains_pii for s in manual_sources)
    combined = "\n".join(s.content for s in manual_sources)
    assert "138 1234 5678" not in combined
    assert "alice@example.com" not in combined
    assert "[REDACTED:phone]" in combined
    assert "[REDACTED:email]" in combined
    assert "团队权限" in combined
    assert "导出能力" in combined


def test_collector_handles_repeat_runs_with_distinct_projects(db_session):
    """Fixture source_ids are static (e.g. src_cursor_001); ensure that
    running the workflow for two different projects against the shared
    SQLite DB does not collide on the Source.id UNIQUE constraint.
    """
    second_project = models.Project(
        id="proj_test_two",
        industry="AI Coding",
        goals="[]",
        status="created",
        output_language="en",
        report_depth="standard",
    )
    db_session.add(second_project)
    db_session.commit()

    first = collector_agent.run(
        db=db_session,
        project_id="proj_test",
        competitors=[{"name": "Cursor", "url": "https://cursor.com"}],
        goals=["pricing_analysis"],
    )
    # Second run with a different project_id but the same fixtures must
    # not raise sqlite3.IntegrityError on sources.id.
    second = collector_agent.run(
        db=db_session,
        project_id="proj_test_two",
        competitors=[{"name": "Cursor", "url": "https://cursor.com"}],
        goals=["pricing_analysis"],
    )

    assert len(first) > 0
    assert len(second) > 0
    # Source IDs returned to the caller are the freshly minted UUIDs,
    # not the static fixture IDs.
    first_ids = {s.source_id for s in first}
    second_ids = {s.source_id for s in second}
    assert first_ids.isdisjoint(second_ids), (
        "Source IDs must be unique across runs"
    )

    # All persisted rows are addressable and the original fixture IDs are
    # preserved in external_id for traceability.
    rows = db_session.query(models.Source).all()
    assert len(rows) == len(first) + len(second)
    external_ids = {row.external_id for row in rows if row.external_id}
    assert external_ids, "external_id should capture the fixture identifier"


def test_collector_repeat_runs_on_same_project_do_not_collide(db_session):
    """Even re-running collection for the *same* project must succeed.
    QA-driven rework triggers exactly this path.
    """
    first = collector_agent.run(
        db=db_session,
        project_id="proj_test",
        competitors=[{"name": "Cursor", "url": "https://cursor.com"}],
        goals=[],
    )
    second = collector_agent.run(
        db=db_session,
        project_id="proj_test",
        competitors=[{"name": "Cursor", "url": "https://cursor.com"}],
        goals=[],
    )
    assert {s.source_id for s in first}.isdisjoint(
        {s.source_id for s in second}
    )


# ---------------------------------------------------------------------------
# demo_scenario=missing_pricing_source rework path
# ---------------------------------------------------------------------------


@pytest.fixture()
def missing_pricing_scenario(monkeypatch):
    """Switch the global settings into the missing_pricing_source mode."""
    monkeypatch.setattr(settings, "demo_scenario", "missing_pricing_source")
    monkeypatch.setattr(
        settings, "demo_withheld_pricing_competitor", "Windsurf"
    )
    yield


def test_collector_withholds_pricing_for_withheld_competitor(
    db_session, missing_pricing_scenario
):
    """Initial collect for Windsurf in missing_pricing_source mode must
    contain NO pricing_page sources — that's what should trigger QA to
    rework.
    """
    sources = collector_agent.run(
        db=db_session,
        project_id="proj_test",
        competitors=[{"name": "Windsurf", "url": "https://codeium.com/windsurf"}],
        goals=["pricing_analysis"],
    )
    assert sources, "Windsurf fixtures should still contain non-pricing pages"
    assert all(
        s.source_type is not SourceType.pricing_page for s in sources
    ), "Pricing page must be withheld initially"
    # Trace record should advertise the withhold so the UI can explain it.
    run_row = (
        db_session.query(models.AgentRun)
        .filter(models.AgentRun.project_id == "proj_test")
        .order_by(models.AgentRun.created_at.desc())
        .first()
    )
    assert "Windsurf" in (run_row.output_json or "")


def test_collector_does_not_withhold_for_other_competitors(
    db_session, missing_pricing_scenario
):
    """Cursor in the same scenario should still get its full fixture set."""
    sources = collector_agent.run(
        db=db_session,
        project_id="proj_test",
        competitors=[{"name": "Cursor", "url": "https://cursor.com"}],
        goals=["pricing_analysis"],
    )
    assert any(
        s.source_type is SourceType.pricing_page for s in sources
    ), "Cursor pricing must be included; only Windsurf is the withheld competitor"


def test_collector_restores_pricing_when_rework_hint_mentions_pricing(
    db_session, missing_pricing_scenario
):
    """Once QA emits a hint about pricing, the next collector pass must
    include the pricing_page source — this is the repair half of the
    demo loop.
    """
    sources = collector_agent.run(
        db=db_session,
        project_id="proj_test",
        competitors=[{"name": "Windsurf", "url": "https://codeium.com/windsurf"}],
        goals=["pricing_analysis"],
        rework_hints=[
            "CollectorAgent must collect the official pricing page for Windsurf"
        ],
    )
    assert any(
        s.source_type is SourceType.pricing_page for s in sources
    ), "Pricing source must be restored when hint mentions pricing"


def test_collector_ignores_unrelated_hint_in_missing_pricing_mode(
    db_session, missing_pricing_scenario
):
    """A hint that doesn't mention pricing should NOT restore the source."""
    sources = collector_agent.run(
        db=db_session,
        project_id="proj_test",
        competitors=[{"name": "Windsurf", "url": "https://codeium.com/windsurf"}],
        goals=["pricing_analysis"],
        rework_hints=["AnalystAgent must add a positioning claim"],
    )
    assert all(s.source_type is not SourceType.pricing_page for s in sources)


def test_happy_path_scenario_does_not_withhold(db_session):
    """In the default happy_path scenario the pricing source is always
    included, regardless of competitor.
    """
    sources = collector_agent.run(
        db=db_session,
        project_id="proj_test",
        competitors=[{"name": "Windsurf", "url": "https://codeium.com/windsurf"}],
        goals=["pricing_analysis"],
    )
    assert any(s.source_type is SourceType.pricing_page for s in sources)
