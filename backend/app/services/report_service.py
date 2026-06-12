"""Report service.

Stores the final or partial :class:`CompetitiveReport` produced by the
WriterAgent and exposes a retrieval helper for the API layer.
"""

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db import models
from app.schemas.report import CompetitiveReport
from app.services.markdown_renderer import render_report_markdown


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
    payload["markdown_content"] = record.markdown_content
    payload["created_at"] = (
        record.created_at.replace(tzinfo=timezone.utc).isoformat()
        if isinstance(record.created_at, datetime)
        else record.created_at
    )
    return payload
