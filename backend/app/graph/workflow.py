"""LangGraph workflow assembly.

Builds the MVP DAG:

```
start
  -> collect_sources
  -> analyze_competitors
  -> write_report
  -> qa_review
  -> if pass: finalize_report -> END
  -> if fail and budget left: handle_rework -> (collect | analyze | write)
  -> if fail and no budget: mark_qa_failed -> END
```

``run_workflow_background`` is the entry point used by the FastAPI
BackgroundTasks runner. It owns initial state construction and the final
error-fallback that flips a project to ``failed`` if a node raises.
"""

from langgraph.graph import END, StateGraph

from app.core.logging import get_logger
from app.graph.nodes import (
    analyze_competitors_node,
    collect_sources_node,
    finalize_report_node,
    handle_rework_node,
    mark_qa_failed_node,
    qa_review_node,
    write_report_node,
)
from app.graph.routing import route_after_qa, route_rework
from app.graph.state import WorkflowState
from app.schemas.project import normalize_analysis_purpose

logger = get_logger(__name__)


def build_workflow():
    """Compile the LangGraph workflow.

    Returns the compiled graph; cached at import-time as
    :data:`competitive_analysis_workflow` for reuse across requests.
    """
    graph: StateGraph = StateGraph(WorkflowState)

    graph.add_node("collect_sources", collect_sources_node)
    graph.add_node("analyze_competitors", analyze_competitors_node)
    graph.add_node("write_report", write_report_node)
    graph.add_node("qa_review", qa_review_node)
    graph.add_node("finalize_report", finalize_report_node)
    graph.add_node("handle_rework", handle_rework_node)
    graph.add_node("mark_qa_failed", mark_qa_failed_node)

    graph.set_entry_point("collect_sources")
    graph.add_edge("collect_sources", "analyze_competitors")
    graph.add_edge("analyze_competitors", "write_report")
    graph.add_edge("write_report", "qa_review")

    graph.add_conditional_edges(
        "qa_review",
        route_after_qa,
        {
            "finalize": "finalize_report",
            "rework": "handle_rework",
            "fail": "mark_qa_failed",
        },
    )
    graph.add_conditional_edges(
        "handle_rework",
        route_rework,
        {
            "collect": "collect_sources",
            "analyze": "analyze_competitors",
            "write": "write_report",
        },
    )
    graph.add_edge("finalize_report", END)
    graph.add_edge("mark_qa_failed", END)

    return graph.compile()


# Compiled once per process. Workflow code paths are stateless; only the
# nodes touch persistent storage via short-lived sessions.
competitive_analysis_workflow = build_workflow()


def _initial_state(
    project_id: str,
    competitors: list[dict],
    goals: list[str],
    output_language: str = "en",
    data_mode: str = "demo",
    industry_type: str = "general",
    analysis_purpose: str = "market_research",
    custom_dimensions: list[str] | None = None,
    research_inputs: list[dict] | None = None,
) -> WorkflowState:
    return {
        "project_id": project_id,
        "competitors": competitors,
        "goals": goals,
        "output_language": output_language,
        "data_mode": data_mode,
        "industry_type": industry_type,
        "analysis_purpose": normalize_analysis_purpose(analysis_purpose),
        "custom_dimensions": custom_dimensions or [],
        "research_inputs": research_inputs or [],
        "sources": [],
        "competitor_knowledge": [],
        "report": None,
        "qa_result": None,
        "rework_count": 0,
        "rework_target": None,
        "rework_hints": [],
        "error": None,
    }


def run_workflow_background(
    project_id: str,
    competitors: list[dict],
    goals: list[str],
    db_url: str | None = None,
    output_language: str = "en",
    data_mode: str = "demo",
    industry_type: str = "general",
    analysis_purpose: str = "market_research",
    custom_dimensions: list[str] | None = None,
    research_inputs: list[dict] | None = None,
) -> None:
    """Entry point invoked by FastAPI BackgroundTasks.

    Args:
        project_id: The project to run analysis for.
        competitors: Competitor list ``[{"name": ..., "url": ...}]``.
        goals: Analysis goals (e.g. ``["pricing_analysis"]``).
        db_url: Optional override (currently unused, kept for symmetry
            with the API contract documented in ``engineering_spec.md``).
        output_language: ISO language code for user-facing report text
            (e.g. ``"en"``, ``"zh"``). Threaded through to WriterAgent.
        data_mode: ``"demo"`` uses fixtures; ``"live_with_fallback"``
            crawls competitor websites and falls back to fixtures when
            coverage is insufficient.
        industry_type: Industry context for source discovery path selection.
        analysis_purpose: Analysis intent — ``"build_similar_product"``,
            ``"choose_product_to_use"``, ``"market_research"``, or
            ``"competitor_success_analysis"``. Controls purpose-specific report sections.
        custom_dimensions: Optional list of user-defined analysis dimensions.
        research_inputs: Optional manually supplied survey/interview/questionnaire notes.
    """
    # ``db_url`` reserved for future per-tenant routing; currently the
    # process-wide engine from ``app.db.session`` is authoritative.
    del db_url

    from app.db.session import SessionLocal
    from app.schemas.project import ProjectStatus, normalize_analysis_purpose
    from app.services import project_service

    logger.info("Starting workflow for project %s", project_id)

    # Flip status to running so the UI can show progress immediately.
    db = SessionLocal()
    try:
        project_service.update_project_status(
            db, project_id, ProjectStatus.running
        )
    finally:
        db.close()

    state = _initial_state(
        project_id, competitors, goals,
        output_language, data_mode, industry_type,
        analysis_purpose, custom_dimensions, research_inputs,
    )
    try:
        competitive_analysis_workflow.invoke(state)
        logger.info("Workflow completed for project %s", project_id)
    except Exception as exc:  # noqa: BLE001 - top-level catch-all
        logger.exception(
            "Workflow failed for project %s: %s", project_id, exc
        )
        db = SessionLocal()
        try:
            project_service.update_project_status(
                db, project_id, ProjectStatus.failed
            )
        finally:
            db.close()
