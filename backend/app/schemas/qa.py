"""QA result schema.

The QAAgent emits a :class:`QAResult` for every report draft. If
``passed`` is false, the workflow inspects the ``issues`` list to route
the rework request to the appropriate upstream agent.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class IssueSeverity(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


# Score deduction per severity. Low = 0 (advisory only, never affects score).
_HIGH_PENALTY: int = 15
_MEDIUM_PENALTY: int = 5


class IssueType(str, Enum):
    missing_source = "missing_source"
    missing_pricing = "missing_pricing"
    missing_pricing_source = "missing_pricing_source"
    missing_features_source = "missing_features_source"
    missing_required_field = "missing_required_field"
    invalid_schema = "invalid_schema"
    weak_evidence = "weak_evidence"
    incomplete_report = "incomplete_report"
    missing_report_section = "missing_report_section"
    missing_citation_in_report = "missing_citation_in_report"
    pricing_inconsistency = "pricing_inconsistency"
    weak_source_quality = "weak_source_quality"
    source_type_content_mismatch = "source_type_content_mismatch"
    brand_mismatch = "brand_mismatch"
    missing_custom_dimension_coverage = "missing_custom_dimension_coverage"
    missing_score_rationale = "missing_score_rationale"
    missing_market_background = "missing_market_background"
    missing_feature_insights = "missing_feature_insights"
    missing_operation_monetization = "missing_operation_monetization"
    weak_data_signal = "weak_data_signal"


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
    score: int = Field(default=100, ge=0, le=100)
    issues: list[QAIssue] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @model_validator(mode="after")
    def _enforce_score_from_issues(self) -> "QAResult":
        """Score is always derived from issues; any manually passed score is overridden.

        Deduction rule: high = -15, medium = -5, low = 0 (advisory only). Floor: 0.
        """
        computed = 100
        for issue in self.issues:
            if issue.severity is IssueSeverity.high:
                computed -= _HIGH_PENALTY
            elif issue.severity is IssueSeverity.medium:
                computed -= _MEDIUM_PENALTY
        self.score = max(computed, 0)
        return self
