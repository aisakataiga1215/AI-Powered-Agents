"""LangGraph node functions.

Each node owns a single phase of the workflow. Nodes:
- Open their own short-lived DB session (LangGraph runs nodes in
  background threads where request-scoped sessions are unavailable).
- Delegate domain work to the business agents in :mod:`app.agents`.
- Return a *partial* state dict update; LangGraph merges it.
- Do not raise on QA failure - QA failure is a normal workflow signal.
"""

from sqlalchemy.orm import Session

from app.agents import analyst_agent
from app.agents import collector_agent
from app.agents import qa_agent
from app.agents import writer_agent
from app.core.logging import get_logger
from app.graph.state import WorkflowState
from app.schemas.project import DEFAULT_ANALYSIS_PURPOSE, ProjectStatus
from app.schemas.qa import IssueSeverity, QAResult
from app.services import project_service, report_service

logger = get_logger(__name__)

# Lower number == higher priority. Issues feeding upstream agents take
# precedence because fixing them invalidates downstream output anyway.
_AGENT_PRIORITY = {
    "CollectorAgent": 0,
    "AnalystAgent": 1,
    "WriterAgent": 2,
}


def _make_db() -> Session:
    from app.db.session import SessionLocal  # lazy import so monkeypatch works in tests
    return SessionLocal()


def collect_sources_node(state: WorkflowState) -> dict:
    """Run the CollectorAgent and return the new sources."""
    db = _make_db()
    try:
        sources = collector_agent.run(
            db=db,
            project_id=state["project_id"],
            competitors=state["competitors"],
            goals=state["goals"],
            rework_hints=state.get("rework_hints", []),
            data_mode=state.get("data_mode", "demo"),
            industry_type=state.get("industry_type", "general"),
            research_inputs=state.get("research_inputs", []),
        )
        return {"sources": sources}
    finally:
        db.close()


def analyze_competitors_node(state: WorkflowState) -> dict:
    """Run the AnalystAgent on the collected sources."""
    db = _make_db()
    try:
        competitor_roles = {
            c["name"]: c.get("role", "direct_competitor")
            for c in state.get("competitors", [])
        }
        knowledge = analyst_agent.run(
            db=db,
            project_id=state["project_id"],
            sources=state["sources"],
            goals=state["goals"],
            rework_hints=state.get("rework_hints", []),
            analysis_purpose=state.get("analysis_purpose", DEFAULT_ANALYSIS_PURPOSE),
            custom_dimensions=state.get("custom_dimensions", []),
            competitor_roles=competitor_roles,
        )
        return {"competitor_knowledge": knowledge}
    finally:
        db.close()


def write_report_node(state: WorkflowState) -> dict:
    """Run the WriterAgent to produce a draft report."""
    db = _make_db()
    try:
        report = writer_agent.run(
            db=db,
            project_id=state["project_id"],
            competitor_knowledge=state["competitor_knowledge"],
            sources=state["sources"],
            goals=state["goals"],
            rework_hints=state.get("rework_hints", []),
            output_language=state.get("output_language", "en"),
            analysis_purpose=state.get("analysis_purpose", DEFAULT_ANALYSIS_PURPOSE),
            custom_dimensions=state.get("custom_dimensions", []),
        )
        return {"report": report}
    finally:
        db.close()


def qa_review_node(state: WorkflowState) -> dict:
    """Run the QAAgent against the latest draft."""
    db = _make_db()
    try:
        result = qa_agent.run(
            db=db,
            project_id=state["project_id"],
            report=state["report"],
            knowledge=state["competitor_knowledge"],
            sources=state["sources"],
            goals=state["goals"],
            analysis_purpose=state.get("analysis_purpose", DEFAULT_ANALYSIS_PURPOSE),
            custom_dimensions=state.get("custom_dimensions", []),
        )
        return {"qa_result": result}
    finally:
        db.close()


def finalize_report_node(state: WorkflowState) -> dict:
    """Persist the final report and mark the project completed."""
    db = _make_db()
    try:
        report = state.get("report")
        if report is not None:
            report_service.save_report(db, state["project_id"], report)
        project_service.update_project_status(
            db, state["project_id"], ProjectStatus.completed
        )
        return {}
    finally:
        db.close()


def handle_rework_node(state: WorkflowState) -> dict:
    """Increment the rework counter and pick a target agent."""
    qa_result = state.get("qa_result")
    rework_count = state.get("rework_count", 0) + 1
    rework_target = _determine_rework_target(qa_result)
    hints = _build_hints(qa_result, rework_target)

    logger.info(
        "handle_rework: project=%s attempt=%d target=%s hints=%d",
        state.get("project_id"),
        rework_count,
        rework_target,
        len(hints),
    )
    return {
        "rework_count": rework_count,
        "rework_target": rework_target,
        "rework_hints": hints,
    }


def mark_qa_failed_node(state: WorkflowState) -> dict:
    """Persist the partial report (if any) and mark the project qa_failed."""
    db = _make_db()
    try:
        report = state.get("report")
        if report is not None:
            report_service.save_report(db, state["project_id"], report)
        project_service.update_project_status(
            db, state["project_id"], ProjectStatus.qa_failed
        )
        return {}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _determine_rework_target(qa_result: QAResult | None) -> str:
    """Pick the most upstream agent referenced by the QA issues.

    Upstream-first prioritization: fixing the collector invalidates the
    analyst's output anyway, so a single high-severity collector issue
    outweighs many writer issues.
    """
    if qa_result is None or not qa_result.issues:
        return "WriterAgent"

    # Prefer agents mentioned by *high* severity issues first, then any.
    high_targets = [
        issue.target_agent
        for issue in qa_result.issues
        if issue.target_agent and issue.severity is IssueSeverity.high
    ]
    candidates = high_targets or [
        issue.target_agent for issue in qa_result.issues if issue.target_agent
    ]
    if not candidates:
        return "WriterAgent"

    return min(candidates, key=lambda t: _AGENT_PRIORITY.get(t, 99))


def _build_hints(qa_result: QAResult | None, target_agent: str) -> list[str]:
    """Collect suggested actions relevant to the rework target."""
    if qa_result is None:
        return []
    hints: list[str] = []
    for issue in qa_result.issues:
        if not issue.suggested_action:
            continue
        # Always include issues targeting this agent, plus any high-severity
        # issues so the downstream agent has full context.
        if (
            issue.target_agent == target_agent
            or issue.severity is IssueSeverity.high
        ):
            hints.append(issue.suggested_action)
    # Deduplicate while preserving order.
    seen: list[str] = []
    for hint in hints:
        if hint not in seen:
            seen.append(hint)
    return seen
