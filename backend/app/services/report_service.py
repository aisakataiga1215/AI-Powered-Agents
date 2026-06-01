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
        created_at=datetime.utcnow(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


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
