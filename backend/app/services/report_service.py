"""Report service.

Stores the final or partial :class:`CompetitiveReport` produced by the
WriterAgent and exposes a retrieval helper for the API layer.
"""

import json
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db import models
from app.schemas.report import CompetitiveReport
from app.services.markdown_renderer import render_report_markdown

_PARAMETER_TAG_RE = re.compile(r"</?parameter[^>]*>", re.IGNORECASE)
_RATIONALE_PARAM_RE = re.compile(
    r"<parameter\s+name=[\"']competitor_selection_rationale[\"'][^>]*>(\{.*?\})(?:\s*</parameter>)?",
    re.IGNORECASE | re.DOTALL,
)


def _clean_function_call_artifacts(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    markers = [idx for idx in (text.find("<parameter"), text.find("</parameter")) if idx >= 0]
    if markers:
        text = text[: min(markers)]
    return _PARAMETER_TAG_RE.sub("", text).strip()


def _extract_rationale_from_objective(value: object) -> dict[str, str]:
    text = str(value or "")
    match = _RATIONALE_PARAM_RE.search(text)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(k): str(v) for k, v in parsed.items() if str(k).strip() and str(v).strip()}


def _sanitize_report_payload(payload: dict) -> dict:
    cleaned = dict(payload)
    embedded_rationale = _extract_rationale_from_objective(cleaned.get("analysis_objective"))
    existing_rationale = cleaned.get("competitor_selection_rationale")
    if embedded_rationale and not (isinstance(existing_rationale, dict) and existing_rationale):
        cleaned["competitor_selection_rationale"] = embedded_rationale
    cleaned["title"] = _clean_function_call_artifacts(cleaned.get("title")) or "Competitive Analysis Report"
    cleaned["analysis_objective"] = _clean_function_call_artifacts(cleaned.get("analysis_objective"))
    for key in ("executive_summary", "strategic_recommendations"):
        claims = cleaned.get(key)
        if isinstance(claims, list):
            for claim in claims:
                if isinstance(claim, dict) and isinstance(claim.get("text"), str):
                    claim["text"] = _clean_function_call_artifacts(claim["text"])
    return cleaned


def _render_human_corrected_markdown(report: CompetitiveReport) -> str:
    """Build markdown from structured report fields after human correction."""
    lines: list[str] = [f"# {report.title}", ""]

    if report.analysis_objective:
        lines.extend(["## Analysis Objective", "", report.analysis_objective, ""])

    if report.executive_summary:
        lines.extend(["## Executive Summary", ""])
        lines.extend(f"- {claim.text}" for claim in report.executive_summary)
        lines.append("")

    if report.competitor_overview:
        lines.extend(["## Competitor Overview", ""])
        for comp in report.competitor_overview:
            lines.append(f"- {comp.competitor_name}")
        lines.append("")

    if report.competitor_selection_rationale:
        lines.extend(["## Competitor Selection Rationale", ""])
        for name, rationale in report.competitor_selection_rationale.items():
            lines.append(f"- **{name}**: {rationale}")
        lines.append("")

    if report.feature_comparison:
        lines.extend(["## Feature Comparison", ""])
        for key, value in report.feature_comparison.items():
            lines.append(f"- **{key}**: {value}")
        lines.append("")

    if report.pricing_comparison:
        lines.extend(["## Pricing Comparison", ""])
        for key, value in report.pricing_comparison.items():
            lines.append(f"- **{key}**: {value}")
        lines.append("")

    if report.user_persona_comparison:
        lines.extend(["## User Personas", "", json.dumps(report.user_persona_comparison, ensure_ascii=False, indent=2), ""])

    if report.swot_comparison:
        lines.extend(["## SWOT", "", json.dumps(report.swot_comparison, ensure_ascii=False, indent=2), ""])

    if report.framework_sections:
        lines.extend(["## Analysis Frameworks", "", json.dumps(report.framework_sections, ensure_ascii=False, indent=2), ""])

    if report.custom_dimension_sections:
        lines.extend(["## Custom Dimensions", "", json.dumps(report.custom_dimension_sections, ensure_ascii=False, indent=2), ""])

    if report.competitor_scores:
        lines.extend(["## Product Selection Scores", ""])
        for name, score in report.competitor_scores.items():
            lines.append(f"- **{name}**: {score.overall_score:.1f}/100")
        lines.append("")

    if report.purpose_sections:
        lines.extend(["## Product Selection Guidance", "", json.dumps(report.purpose_sections, ensure_ascii=False, indent=2), ""])

    if report.strategic_recommendations:
        lines.extend(["## Strategic Recommendations", ""])
        lines.extend(f"- {claim.text}" for claim in report.strategic_recommendations)
        lines.append("")

    report.markdown_content = "\n".join(lines).strip()
    return render_report_markdown(report)


def save_report(
    db: Session,
    project_id: str,
    report: CompetitiveReport,
) -> models.Report:
    """Persist a report. One project may have multiple draft reports;
    callers typically keep only the most recent.
    """
    report_id = report.report_id or f"rpt_{uuid.uuid4().hex[:8]}"
    json_payload = report.model_dump(mode="json")
    record = models.Report(
        id=report_id,
        project_id=project_id,
        markdown_content=report.markdown_content,
        json_content=json.dumps(json_payload, ensure_ascii=False),
        created_at=datetime.now(timezone.utc),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def save_report_from_payload(
    db: Session,
    project_id: str,
    payload: dict,
) -> models.Report:
    """Validate and persist a report payload as a new revision."""
    payload["project_id"] = project_id
    payload.pop("report_id", None)
    payload.pop("created_at", None)
    payload = _sanitize_report_payload(payload)
    report = CompetitiveReport.model_validate(payload)
    report.markdown_content = _render_human_corrected_markdown(report)
    return save_report(db, project_id, report)


def get_report(db: Session, project_id: str) -> models.Report | None:
    """Return the most recent report for a project, if any."""
    return (
        db.query(models.Report)
        .filter(models.Report.project_id == project_id)
        .order_by(models.Report.created_at.desc())
        .first()
    )


def serialize_report(record: models.Report) -> dict:
    try:
        payload = json.loads(record.json_content or "{}")
    except json.JSONDecodeError:
        payload = {}
    payload["report_id"] = record.id
    payload["project_id"] = record.project_id
    payload = _sanitize_report_payload(payload)
    try:
        report = CompetitiveReport.model_validate(payload)
        payload["markdown_content"] = _render_human_corrected_markdown(report)
    except Exception:
        payload["markdown_content"] = record.markdown_content
    payload["created_at"] = (
        record.created_at.replace(tzinfo=timezone.utc).isoformat()
        if isinstance(record.created_at, datetime)
        else record.created_at
    )
    return payload
