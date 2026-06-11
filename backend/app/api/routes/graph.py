"""Workflow graph route.

Exposes the compiled LangGraph DAG to the frontend so the UI cannot drift
from the backend workflow definition.
"""

from fastapi import APIRouter

from app.graph.workflow import competitive_analysis_workflow

router = APIRouter()


_LABELS: dict[str, str] = {
    "__start__": "Start",
    "collect_sources": "Collector",
    "analyze_competitors": "Analyst",
    "write_report": "Writer",
    "qa_review": "QA",
    "finalize_report": "Finalize",
    "handle_rework": "Rework Router",
    "mark_qa_failed": "QA Failed",
    "__end__": "End",
}


def _node_type(node_id: str) -> str:
    if node_id in {"__start__", "__end__"}:
        return "terminal"
    if node_id in {"handle_rework", "finalize_report", "mark_qa_failed"}:
        return "router"
    return "agent"


@router.get("/graph")
def get_graph() -> dict:
    graph_json = competitive_analysis_workflow.get_graph().to_json()
    raw_nodes = graph_json.get("nodes", [])
    raw_edges = graph_json.get("edges", [])

    nodes: list[dict] = []
    for node in raw_nodes:
        node_id = str(node.get("id") or "")
        if not node_id:
            continue
        nodes.append({
            "id": node_id,
            "label": _LABELS.get(node_id, node_id.replace("_", " ").title()),
            "type": _node_type(node_id),
        })

    edges: list[dict] = []
    for edge in raw_edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if not source or not target:
            continue
        condition = edge.get("conditional") or edge.get("condition")
        payload = {"source": source, "target": target}
        if condition:
            payload["condition"] = str(condition)
        edges.append(payload)

    return {"nodes": nodes, "edges": edges}
