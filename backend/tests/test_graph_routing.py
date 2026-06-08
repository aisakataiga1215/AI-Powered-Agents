"""LangGraph routing and rework target unit tests.

These tests do not invoke the LLM, the DB, or the compiled graph. They
verify the pure routing helpers that decide:

- After QA: finalize vs rework vs fail
- After rework: which node to re-enter
- Which agent owns a rework loop given a set of QA issues
"""

import pytest

from app.core.config import settings
from app.graph import nodes, routing
from app.graph.state import WorkflowState
from app.schemas.qa import IssueSeverity, IssueType, QAIssue, QAResult


def _state_with_qa(
    *,
    passed: bool,
    rework_count: int = 0,
    issues: list[QAIssue] | None = None,
    score: int = 60,
) -> WorkflowState:
    qa_result = QAResult(
        project_id="proj_1",
        passed=passed,
        score=score,
        issues=issues or [],
    )
    state: WorkflowState = {
        "project_id": "proj_1",
        "competitors": [],
        "goals": [],
        "sources": [],
        "competitor_knowledge": [],
        "report": None,
        "qa_result": qa_result,
        "rework_count": rework_count,
        "rework_target": None,
        "rework_hints": [],
        "error": None,
    }
    return state


# ---------------------------------------------------------------------------
# route_after_qa
# ---------------------------------------------------------------------------


def test_route_after_qa_finalize_when_passed():
    state = _state_with_qa(passed=True, score=92)
    assert routing.route_after_qa(state) == "finalize"


def test_route_after_qa_rework_when_failed_with_budget():
    state = _state_with_qa(passed=False, rework_count=0)
    # ``max_repair_loops`` default is 1; rework_count=0 leaves room.
    assert routing.route_after_qa(state) == "rework"


def test_route_after_qa_fail_when_budget_exhausted():
    state = _state_with_qa(
        passed=False, rework_count=settings.max_repair_loops
    )
    assert routing.route_after_qa(state) == "fail"


def test_route_after_qa_fail_when_qa_result_missing():
    state: WorkflowState = {
        "project_id": "proj_1",
        "competitors": [],
        "goals": [],
        "sources": [],
        "competitor_knowledge": [],
        "report": None,
        "qa_result": None,
        "rework_count": 0,
        "rework_target": None,
        "rework_hints": [],
        "error": None,
    }
    assert routing.route_after_qa(state) == "fail"


# ---------------------------------------------------------------------------
# route_rework
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "target,expected",
    [
        ("CollectorAgent", "collect"),
        ("AnalystAgent", "analyze"),
        ("WriterAgent", "write"),
        (None, "write"),
        ("Unknown", "write"),
    ],
)
def test_route_rework_mapping(target, expected):
    state: WorkflowState = {
        "project_id": "proj_1",
        "competitors": [],
        "goals": [],
        "sources": [],
        "competitor_knowledge": [],
        "report": None,
        "qa_result": None,
        "rework_count": 1,
        "rework_target": target,
        "rework_hints": [],
        "error": None,
    }
    assert routing.route_rework(state) == expected


# ---------------------------------------------------------------------------
# _determine_rework_target
# ---------------------------------------------------------------------------


def test_determine_rework_target_prefers_upstream_agent():
    qa = QAResult(
        project_id="proj_1",
        passed=False,
        score=40,
        issues=[
            QAIssue(
                severity=IssueSeverity.high,
                issue_type=IssueType.missing_citation_in_report,
                target_agent="WriterAgent",
                message="claim has no evidence",
            ),
            QAIssue(
                severity=IssueSeverity.high,
                issue_type=IssueType.missing_source,
                target_agent="CollectorAgent",
                message="no sources",
            ),
        ],
    )
    assert nodes._determine_rework_target(qa) == "CollectorAgent"


def test_determine_rework_target_falls_back_to_writer_on_empty():
    qa = QAResult(project_id="proj_1", passed=False, score=80, issues=[])
    assert nodes._determine_rework_target(qa) == "WriterAgent"


def test_determine_rework_target_prefers_high_severity_over_medium():
    qa = QAResult(
        project_id="proj_1",
        passed=False,
        score=70,
        issues=[
            QAIssue(
                severity=IssueSeverity.medium,
                issue_type=IssueType.weak_evidence,
                target_agent="CollectorAgent",
                message="weakish",
            ),
            QAIssue(
                severity=IssueSeverity.high,
                issue_type=IssueType.missing_report_section,
                target_agent="WriterAgent",
                message="bad",
            ),
        ],
    )
    # High severity wins even though CollectorAgent would be more upstream
    # at the priority table; this matches the suggested-action contract
    # where the QA agent assigns target_agent per issue.
    assert nodes._determine_rework_target(qa) == "WriterAgent"


def test_determine_rework_target_none_input():
    assert nodes._determine_rework_target(None) == "WriterAgent"


# ---------------------------------------------------------------------------
# _build_hints
# ---------------------------------------------------------------------------


def test_build_hints_dedupes_and_filters_blanks():
    qa = QAResult(
        project_id="proj_1",
        passed=False,
        score=40,
        issues=[
            QAIssue(
                severity=IssueSeverity.high,
                issue_type=IssueType.missing_source,
                target_agent="CollectorAgent",
                message="x",
                suggested_action="Collect pricing page",
            ),
            QAIssue(
                severity=IssueSeverity.high,
                issue_type=IssueType.missing_source,
                target_agent="CollectorAgent",
                message="y",
                suggested_action="Collect pricing page",
            ),
            QAIssue(
                severity=IssueSeverity.medium,
                issue_type=IssueType.weak_evidence,
                target_agent="WriterAgent",
                message="z",
                suggested_action="",
            ),
        ],
    )
    hints = nodes._build_hints(qa, target_agent="CollectorAgent")
    assert hints == ["Collect pricing page"]


def test_build_hints_includes_high_severity_from_other_agents():
    qa = QAResult(
        project_id="proj_1",
        passed=False,
        score=40,
        issues=[
            QAIssue(
                severity=IssueSeverity.high,
                issue_type=IssueType.missing_report_section,
                target_agent="WriterAgent",
                message="missing summary",
                suggested_action="Add executive_summary",
            ),
        ],
    )
    hints = nodes._build_hints(qa, target_agent="CollectorAgent")
    # The high severity writer issue is still surfaced as context to the
    # collector so it can collect a fix-supporting source if needed.
    assert "Add executive_summary" in hints
