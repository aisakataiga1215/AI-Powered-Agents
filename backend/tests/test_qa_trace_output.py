"""Lightweight unit tests for QAAgent._build_trace_output.

Tests exercise the helper directly — no database setup required.
The invariants being verified:

1. The trace output always includes the ``issues`` list.
2. ``len(issues) == issue_count`` (consistency between array and scalar).
3. ``score < 100`` implies ``blocking_issue_count > 0`` because the
   ``@model_validator`` on ``QAResult`` only deducts for high/medium
   severity; low severity is advisory-only (0 deduction).
"""

import pytest

from app.agents.qa_agent import _build_trace_output
from app.schemas.qa import IssueSeverity, IssueType, QAIssue, QAResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _issue(severity: IssueSeverity) -> QAIssue:
    return QAIssue(
        severity=severity,
        issue_type=IssueType.missing_required_field,
        target_agent="WriterAgent",
        message=f"{severity.value} test issue",
    )


def _result(issues: list[QAIssue]) -> QAResult:
    return QAResult(project_id="proj_test", passed=False, issues=issues)


# ---------------------------------------------------------------------------
# Test 1: issues array is always present
# ---------------------------------------------------------------------------


def test_qa_trace_output_includes_issues_array():
    issues = [_issue(IssueSeverity.high), _issue(IssueSeverity.medium)]
    result = _result(issues)
    output = _build_trace_output(result, issues)

    assert "issues" in output
    assert isinstance(output["issues"], list)
    assert len(output["issues"]) == 2
    # Each entry should be a dict with expected keys
    first = output["issues"][0]
    assert "severity" in first
    assert "message" in first
    assert "target_agent" in first


# ---------------------------------------------------------------------------
# Test 2: issue_count matches len(issues)
# ---------------------------------------------------------------------------


def test_qa_trace_issue_count_matches_issues_array_length():
    issues = [_issue(IssueSeverity.high), _issue(IssueSeverity.low), _issue(IssueSeverity.low)]
    result = _result(issues)
    output = _build_trace_output(result, issues)

    assert output["issue_count"] == len(output["issues"])
    assert output["issue_count"] == 3
    assert output["high_severity_count"] == 1
    assert output["medium_severity_count"] == 0
    assert output["low_severity_count"] == 2
    assert output["blocking_issue_count"] == 1
    assert output["advisory_count"] == 2


# ---------------------------------------------------------------------------
# Test 3: score < 100 implies at least one blocking issue
# ---------------------------------------------------------------------------


def test_qa_trace_score_below_100_implies_blocking_issue():
    # High issue deducts 15 points → score = 85
    issues = [_issue(IssueSeverity.high)]
    result = _result(issues)
    output = _build_trace_output(result, issues)

    assert output["score"] < 100
    assert output["blocking_issue_count"] > 0, (
        "score < 100 must be backed by at least one high or medium issue; "
        "low-severity advisories carry 0 deduction per QAResult model_validator"
    )


# ---------------------------------------------------------------------------
# Test 4: advisory-only → score stays 100
# ---------------------------------------------------------------------------


def test_qa_trace_advisory_only_does_not_reduce_score():
    # Only low severity issues; score must remain 100
    issues = [_issue(IssueSeverity.low), _issue(IssueSeverity.low)]
    result = _result(issues)
    output = _build_trace_output(result, issues)

    assert output["score"] == 100
    assert output["blocking_issue_count"] == 0
    assert output["advisory_count"] == 2


# ---------------------------------------------------------------------------
# Test 5: empty issues → all counts zero
# ---------------------------------------------------------------------------


def test_qa_trace_no_issues_produces_zero_counts():
    result = _result([])
    output = _build_trace_output(result, [])

    assert output["issue_count"] == 0
    assert output["issues"] == []
    assert output["high_severity_count"] == 0
    assert output["medium_severity_count"] == 0
    assert output["low_severity_count"] == 0
    assert output["blocking_issue_count"] == 0
    assert output["advisory_count"] == 0
    assert output["score"] == 100
