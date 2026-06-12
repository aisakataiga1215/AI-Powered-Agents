"""LangGraph workflow state.

A single :class:`WorkflowState` flows through every node. Nodes return a
partial dict update that LangGraph merges into the canonical state.
"""

from typing import Optional, TypedDict

from app.schemas.knowledge import CompetitorKnowledge
from app.schemas.qa import QAResult
from app.schemas.report import CompetitiveReport
from app.schemas.source import SourceEvidence


class WorkflowState(TypedDict, total=False):
    """Mutable state for the competitive analysis LangGraph workflow.

    All keys are optional from the type system's perspective so that node
    return dicts can do partial updates. The runtime invariant is that
    ``project_id``, ``competitors``, and ``goals`` are always present
    after :func:`workflow.run_workflow_background` seeds the graph.
    """

    project_id: str
    competitors: list[dict]  # [{"name": str, "url": str}]
    goals: list[str]
    analysis_frameworks: list[str]
    output_language: str
    data_mode: str  # "demo" | "live_with_fallback"
    industry_type: str  # "ai_saas" | "ecommerce" | "local_services" | "social" | "general"
    analysis_purpose: str  # decision-support purpose, e.g. "build_product"
    custom_dimensions: list[str]
    research_inputs: list[dict]
    sources: list[SourceEvidence]
    competitor_knowledge: list[CompetitorKnowledge]
    report: Optional[CompetitiveReport]
    previous_report: Optional[CompetitiveReport]
    qa_result: Optional[QAResult]
    rework_count: int
    rework_target: Optional[str]  # "CollectorAgent" | "AnalystAgent" | "WriterAgent"
    rework_hints: list[str]
    error: Optional[str]
