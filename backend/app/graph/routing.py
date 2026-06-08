"""LangGraph conditional routing logic.

Pure functions that inspect the :class:`WorkflowState` and decide the
next node label. Routing is intentionally separated from node side
effects so the routing rules can be unit-tested without touching the
database or the LLM.
"""

from app.core.config import settings
from app.core.logging import get_logger
from app.graph.state import WorkflowState

logger = get_logger(__name__)


def route_after_qa(state: WorkflowState) -> str:
    """Decide what to do after QA has produced a result.

    Returns one of:
    - ``"finalize"`` when QA passed
    - ``"rework"`` when QA failed and rework budget remains
    - ``"fail"`` when QA failed and rework budget is exhausted
    """
    qa_result = state.get("qa_result")
    if qa_result is None:
        logger.warning("route_after_qa: missing qa_result, marking as failed")
        return "fail"

    if qa_result.passed:
        return "finalize"

    rework_count = state.get("rework_count", 0)
    if rework_count >= settings.max_repair_loops:
        logger.info(
            "route_after_qa: rework budget exhausted (%d/%d), failing",
            rework_count,
            settings.max_repair_loops,
        )
        return "fail"

    return "rework"


def route_rework(state: WorkflowState) -> str:
    """Map a rework target Agent name back to the workflow node label."""
    target = state.get("rework_target") or "WriterAgent"
    mapping = {
        "CollectorAgent": "collect",
        "AnalystAgent": "analyze",
        "WriterAgent": "write",
    }
    return mapping.get(target, "write")
