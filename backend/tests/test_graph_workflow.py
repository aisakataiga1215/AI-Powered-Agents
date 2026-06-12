"""LangGraph workflow assembly and rework-cycle integration tests.

The smoke tests verify that the compiled graph can be built and that the
module-level singleton exposes the expected runtime contract.

The integration test exercises the end-to-end rework cycle (QA fails →
rework routes back to collector → second pass passes → report finalized)
with the four business agents replaced by deterministic fakes. This is
the test backing requirements 4, 6, 7, and 8 of the rework-path spec:

- Workflow must route back to CollectorAgent once QA flags missing pricing
- AnalystAgent and WriterAgent rerun after the rework
- QA passes on the repaired output
- Both QA runs are persisted so the trace API can show them
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents import (
    analyst_agent,
    collector_agent,
    qa_agent,
    writer_agent,
)
from app.db import models
from app.graph import nodes as graph_nodes
from app.graph.workflow import (
    _initial_state,
    build_workflow,
    competitive_analysis_workflow,
)
from app.schemas.claim import Claim
from app.schemas.knowledge import (
    CompetitorKnowledge,
    FeatureCategory,
    FeatureItem,
    PricingModel,
    PricingPlan,
    ProductProfile,
)
from app.schemas.qa import IssueSeverity, IssueType, QAIssue, QAResult
from app.schemas.report import CompetitiveReport
from app.schemas.source import Reliability, SourceEvidence, SourceType


def test_workflow_compiles_without_error():
    """Re-building must succeed; this exercises every add_node call."""
    graph = build_workflow()
    assert graph is not None
    assert hasattr(graph, "invoke")


def test_workflow_module_level_singleton_compiled():
    """The cached singleton must be ready for invoke() at import time."""
    assert competitive_analysis_workflow is not None
    assert hasattr(competitive_analysis_workflow, "invoke")


def test_initial_state_normalizes_legacy_analysis_purpose():
    state = _initial_state(
        project_id="proj_legacy",
        competitors=[],
        goals=[],
        analysis_purpose="choose_product",
    )

    assert state["analysis_purpose"] == "choose_product"


# ---------------------------------------------------------------------------
# Rework-cycle integration test
# ---------------------------------------------------------------------------


def _make_source(source_id: str, source_type: SourceType) -> SourceEvidence:
    return SourceEvidence(
        source_id=source_id,
        competitor_name="Windsurf",
        source_type=source_type,
        url=f"https://codeium.com/{source_id}",
        title=f"{source_id} title",
        snippet="",
        content="",
        reliability=Reliability.high,
    )


def _make_knowledge(
    source_ids: list[str],
    pricing: bool,
) -> CompetitorKnowledge:
    return CompetitorKnowledge(
        competitor_id="comp_1",
        competitor_name="Windsurf",
        product_profile=ProductProfile(
            name="Windsurf",
            website="https://codeium.com/windsurf",
            positioning=Claim(text="AI IDE", evidence=[source_ids[0]]),
        ),
        feature_tree=[
            FeatureCategory(
                category="AI Coding",
                features=[
                    FeatureItem(
                        name="Flows",
                        availability="available",
                        evidence=[source_ids[0]],
                    )
                ],
            )
        ],
        pricing_model=(
            PricingModel(
                has_free_plan=True,
                plans=[PricingPlan(name="Pro", price="$10")],
            )
            if pricing
            else None
        ),
        sources=source_ids,
    )


def _make_report(
    knowledge: CompetitorKnowledge,
    sources: list[SourceEvidence],
    pricing_comparison: dict,
) -> CompetitiveReport:
    primary_id = sources[0].source_id
    return CompetitiveReport(
        project_id="proj_rework",
        executive_summary=[
            Claim(text="Windsurf is rising fast", evidence=[primary_id])
        ],
        competitor_overview=[knowledge],
        feature_comparison={"AI Coding": {"Windsurf": "available"}},
        pricing_comparison=pricing_comparison,
        swot_comparison={"Windsurf": "Strong flows"},
        strategic_recommendations=[
            Claim(text="Bundle pricing", evidence=[primary_id])
        ],
        source_list=sources,
    )


@pytest.fixture()
def rework_db(monkeypatch):
    """Provision an in-memory SQLite DB and route every node to it."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    models.Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine, autocommit=False, autoflush=False
    )

    project = session_factory()
    project.add(
        models.Project(
            id="proj_rework",
            industry="AI Coding",
            goals='["pricing_analysis"]',
            status="created",
            output_language="en",
            report_depth="standard",
        )
    )
    project.commit()
    project.close()

    # ``_make_db`` is what every node uses to open a session. Point it at
    # our in-memory engine so persistence assertions are observable here.
    monkeypatch.setattr(graph_nodes, "_make_db", session_factory)

    yield session_factory
    engine.dispose()


def test_rework_cycle_collector_repairs_missing_pricing(rework_db, monkeypatch):
    """Full QA→rework→repair cycle.

    Fakes drive the business agents so we can prove the routing without
    talking to an LLM:

    1. First collector pass returns one non-pricing source (mimics the
       ``missing_pricing_source`` demo scenario).
    2. First analyst pass yields knowledge with no pricing_model.plans.
    3. First writer pass emits a report referencing only the collected
       source.
    4. First QA result fails with a high-severity ``missing_pricing``
       issue targeting CollectorAgent.
    5. handle_rework increments rework_count, routes back to collector
       with a hint.
    6. Second collector pass returns the pricing source as well.
    7. Second analyst pass yields full knowledge with a pricing plan.
    8. Second writer pass emits a complete report.
    9. Second QA result passes → finalize_report runs.
    10. Project is marked ``completed`` and the report row is persisted.
    """
    pricing_src = _make_source("src_pricing_01", SourceType.pricing_page)
    home_src = _make_source("src_home_01", SourceType.official_website)

    # --- Collector fake -----------------------------------------------------
    collector_calls: list[dict] = []

    def fake_collector(
        db,
        project_id,
        competitors,
        goals,
        rework_hints=None,
        data_mode="demo",
        industry_type="general",
        research_inputs=None,
    ):
        call = {
            "attempt": len(collector_calls) + 1,
            "rework_hints": list(rework_hints or []),
        }
        collector_calls.append(call)
        if call["attempt"] == 1:
            return [home_src]
        # Repair pass: pricing source is now included.
        return [home_src, pricing_src]

    # --- Analyst fake -------------------------------------------------------
    analyst_calls: list[dict] = []

    def fake_analyst(db, project_id, sources, goals, rework_hints=None, **kwargs):
        analyst_calls.append({"source_count": len(sources)})
        has_pricing_source = any(
            s.source_type is SourceType.pricing_page for s in sources
        )
        ids = [s.source_id for s in sources]
        return [_make_knowledge(ids, pricing=has_pricing_source)]

    # --- Writer fake --------------------------------------------------------
    writer_calls: list[dict] = []

    def fake_writer(
        db,
        project_id,
        competitor_knowledge,
        sources,
        goals,
        rework_hints=None,
        output_language="en",
        **kwargs,
    ):
        writer_calls.append({"source_count": len(sources)})
        knowledge = competitor_knowledge[0]
        has_pricing = bool(knowledge.pricing_model and knowledge.pricing_model.plans)
        pricing_comparison = (
            {"Windsurf": "Pro at $10/mo"} if has_pricing else {}
        )
        return _make_report(knowledge, sources, pricing_comparison)

    # --- QA fake ------------------------------------------------------------
    qa_calls: list[dict] = []

    def fake_qa(db, project_id, report, knowledge, sources, goals, **kwargs):
        attempt = len(qa_calls) + 1
        has_pricing_source = any(
            s.source_type is SourceType.pricing_page for s in sources
        )
        qa_calls.append(
            {
                "attempt": attempt,
                "has_pricing_source": has_pricing_source,
            }
        )
        if not has_pricing_source:
            result = QAResult(
                project_id=project_id,
                passed=False,
                score=70,
                issues=[
                    QAIssue(
                        severity=IssueSeverity.high,
                        issue_type=IssueType.missing_pricing,
                        target_agent="CollectorAgent",
                        message="No pricing_page source for Windsurf",
                        suggested_action=(
                            "CollectorAgent must collect the official "
                            "pricing page for Windsurf"
                        ),
                    )
                ],
            )
        else:
            result = QAResult(
                project_id=project_id,
                passed=True,
                score=95,
                issues=[],
            )
        # Persist the QA result so the trace API can surface both passes.
        from app.services import qa_service

        qa_service.save_qa_result(db, result)
        return result

    monkeypatch.setattr(collector_agent, "run", fake_collector)
    monkeypatch.setattr(analyst_agent, "run", fake_analyst)
    monkeypatch.setattr(writer_agent, "run", fake_writer)
    monkeypatch.setattr(qa_agent, "run", fake_qa)

    initial_state = {
        "project_id": "proj_rework",
        "competitors": [
            {"name": "Windsurf", "url": "https://codeium.com/windsurf"}
        ],
        "goals": ["pricing_analysis"],
        "sources": [],
        "competitor_knowledge": [],
        "report": None,
        "qa_result": None,
        "rework_count": 0,
        "rework_target": None,
        "rework_hints": [],
        "error": None,
    }

    final_state = competitive_analysis_workflow.invoke(initial_state)

    # Each business agent ran exactly twice (once + one rework pass).
    assert len(collector_calls) == 2
    assert len(analyst_calls) == 2
    assert len(writer_calls) == 2
    assert len(qa_calls) == 2

    # The first collector pass got no rework hints; the second pass did.
    assert collector_calls[0]["rework_hints"] == []
    assert collector_calls[1]["rework_hints"], (
        "rework hints must be propagated to the second collector pass"
    )
    assert any(
        "pricing" in hint.lower()
        for hint in collector_calls[1]["rework_hints"]
    ), "the rework hint that triggered the repair must mention pricing"

    # First QA call saw no pricing source; second call did.
    assert qa_calls[0]["has_pricing_source"] is False
    assert qa_calls[1]["has_pricing_source"] is True

    # Final QA result on the merged state is the passing one.
    assert final_state["qa_result"].passed is True
    assert final_state["rework_count"] == 1
    assert final_state["rework_target"] == "CollectorAgent"

    # The finalize node ran: project status flipped to completed and the
    # report was written.
    session = rework_db()
    try:
        project = (
            session.query(models.Project)
            .filter(models.Project.id == "proj_rework")
            .first()
        )
        assert project is not None
        assert project.status == "completed"

        report_rows = (
            session.query(models.Report)
            .filter(models.Report.project_id == "proj_rework")
            .all()
        )
        assert len(report_rows) == 1

        qa_rows = (
            session.query(models.QAResultRecord)
            .filter(models.QAResultRecord.project_id == "proj_rework")
            .order_by(models.QAResultRecord.created_at.asc())
            .all()
        )
        assert len(qa_rows) == 2, (
            "both the failing and the repaired QA result must be visible "
            "to the trace API"
        )
        assert qa_rows[0].passed is False
        assert qa_rows[1].passed is True
    finally:
        session.close()


def test_rework_budget_exhaustion_marks_project_qa_failed(
    rework_db, monkeypatch
):
    """If QA keeps failing past ``max_repair_loops`` we must fail closed.

    Guards the contract that the workflow never spins indefinitely: once
    the rework budget is exhausted the project lands in ``qa_failed`` and
    the partial report is still persisted so the user can inspect what
    went wrong.
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_repair_loops", 1)

    home_src = _make_source("src_home_01", SourceType.official_website)

    def fake_collector(
        db,
        project_id,
        competitors,
        goals,
        rework_hints=None,
        data_mode="demo",
        industry_type="general",
        research_inputs=None,
    ):
        return [home_src]

    def fake_analyst(db, project_id, sources, goals, rework_hints=None, **kwargs):
        ids = [s.source_id for s in sources]
        return [_make_knowledge(ids, pricing=False)]

    def fake_writer(
        db,
        project_id,
        competitor_knowledge,
        sources,
        goals,
        rework_hints=None,
        output_language="en",
        **kwargs,
    ):
        return _make_report(competitor_knowledge[0], sources, {})

    qa_attempts: list[int] = []

    def fake_qa(db, project_id, report, knowledge, sources, goals, **kwargs):
        qa_attempts.append(len(qa_attempts) + 1)
        return QAResult(
            project_id=project_id,
            passed=False,
            score=50,
            issues=[
                QAIssue(
                    severity=IssueSeverity.high,
                    issue_type=IssueType.missing_pricing,
                    target_agent="CollectorAgent",
                    message="No pricing_page source for Windsurf",
                    suggested_action="CollectorAgent must collect pricing",
                )
            ],
        )

    monkeypatch.setattr(collector_agent, "run", fake_collector)
    monkeypatch.setattr(analyst_agent, "run", fake_analyst)
    monkeypatch.setattr(writer_agent, "run", fake_writer)
    monkeypatch.setattr(qa_agent, "run", fake_qa)

    initial_state = {
        "project_id": "proj_rework",
        "competitors": [
            {"name": "Windsurf", "url": "https://codeium.com/windsurf"}
        ],
        "goals": ["pricing_analysis"],
        "sources": [],
        "competitor_knowledge": [],
        "report": None,
        "qa_result": None,
        "rework_count": 0,
        "rework_target": None,
        "rework_hints": [],
        "error": None,
    }

    final_state = competitive_analysis_workflow.invoke(initial_state)

    # QA ran once before rework, then one more time after the only allowed
    # rework attempt. The second failure exhausts the budget.
    assert len(qa_attempts) == 2
    assert final_state["qa_result"].passed is False
    assert final_state["rework_count"] == 1

    session = rework_db()
    try:
        project = (
            session.query(models.Project)
            .filter(models.Project.id == "proj_rework")
            .first()
        )
        assert project.status == "qa_failed"
        # Partial report should still be persisted so the user can see why.
        report_rows = (
            session.query(models.Report)
            .filter(models.Report.project_id == "proj_rework")
            .all()
        )
        assert len(report_rows) == 1
    finally:
        session.close()
