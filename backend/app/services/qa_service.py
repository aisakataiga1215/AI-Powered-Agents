"""QA service.

Persists :class:`QAResult` validation outputs from the QAAgent.
"""

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db import models
from app.schemas.qa import QAResult


def save_qa_result(db: Session, result: QAResult) -> models.QAResultRecord:
    issues_payload = [issue.model_dump() for issue in result.issues]
    record = models.QAResultRecord(
        id=result.qa_result_id,
        project_id=result.project_id,
        passed=result.passed,
        score=result.score,
        issues_json=json.dumps(issues_payload, ensure_ascii=False),
        created_at=datetime.utcnow(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_qa_results(
    db: Session,
    project_id: str,
) -> list[models.QAResultRecord]:
    return (
        db.query(models.QAResultRecord)
        .filter(models.QAResultRecord.project_id == project_id)
        .order_by(models.QAResultRecord.created_at.asc())
        .all()
    )


def serialize_qa_result(record: models.QAResultRecord) -> dict:
    try:
        issues = json.loads(record.issues_json or "[]")
    except json.JSONDecodeError:
        issues = []
    return {
        "qa_result_id": record.id,
        "project_id": record.project_id,
        "passed": record.passed,
        "score": record.score,
        "issues": issues,
        "created_at": record.created_at.replace(tzinfo=timezone.utc).isoformat()
        if isinstance(record.created_at, datetime)
        else record.created_at,
    }
