"""QA result schema.

The QAAgent emits a :class:`QAResult` for every report draft. If
``passed`` is false, the workflow inspects the ``issues`` list to route
the rework request to the appropriate upstream agent.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class IssueSeverity(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class IssueType(str, Enum):
    missing_source = "missing_source"
    missing_pricing = "missing_pricing"
    missing_required_field = "missing_required_field"
    invalid_schema = "invalid_schema"
    weak_evidence = "weak_evidence"
    incomplete_report = "incomplete_report"
    missing_report_section = "missing_report_section"
    missing_citation_in_report = "missing_citation_in_report"
    pricing_inconsistency = "pricing_inconsistency"


class QAIssue(BaseModel):
    issue_id: str = Field(default_factory=lambda: f"issue_{uuid.uuid4().hex[:8]}")
    severity: IssueSeverity
    issue_type: IssueType
    target_agent: str  # "CollectorAgent" | "AnalystAgent" | "WriterAgent"
    message: str
    suggested_action: str = ""


class QAResult(BaseModel):
    qa_result_id: str = Field(default_factory=lambda: f"qa_{uuid.uuid4().hex[:8]}")
    project_id: str
    passed: bool
    score: int = Field(ge=0, le=100)
    issues: list[QAIssue] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
