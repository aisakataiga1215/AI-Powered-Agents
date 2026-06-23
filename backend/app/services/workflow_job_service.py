"""Workflow job persistence and concurrency control.

The MVP still uses FastAPI BackgroundTasks as the local execution adapter,
but route handlers now create a durable workflow job first. Production can
replace the adapter with Celery/RQ/Dramatiq while keeping this persistence
contract and project-level lock.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db import models
from app.schemas.job import WorkflowJobResponse, WorkflowJobStatus

ACTIVE_STATUSES = {
    WorkflowJobStatus.queued.value,
    WorkflowJobStatus.running.value,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_active_job(
    db: Session,
    project_id: str,
) -> models.WorkflowJob | None:
    return (
        db.query(models.WorkflowJob)
        .filter(
            models.WorkflowJob.project_id == project_id,
            models.WorkflowJob.status.in_(ACTIVE_STATUSES),
        )
        .order_by(models.WorkflowJob.created_at.desc())
        .first()
    )


def create_job(
    db: Session,
    *,
    project_id: str,
    payload: dict[str, Any],
    backend: str = "background_tasks",
) -> models.WorkflowJob:
    job = models.WorkflowJob(
        id=f"job_{uuid.uuid4().hex[:12]}",
        project_id=project_id,
        status=WorkflowJobStatus.queued.value,
        backend=backend,
        payload_json=json.dumps(payload, ensure_ascii=False),
        attempts=0,
        created_at=_now(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def mark_running(db: Session, job_id: str) -> models.WorkflowJob | None:
    job = db.query(models.WorkflowJob).filter(models.WorkflowJob.id == job_id).first()
    if job is None:
        return None
    if job.status == WorkflowJobStatus.canceled.value:
        return job
    job.status = WorkflowJobStatus.running.value
    job.attempts = int(job.attempts or 0) + 1
    job.started_at = _now()
    db.commit()
    db.refresh(job)
    return job


def mark_completed(db: Session, job_id: str) -> models.WorkflowJob | None:
    job = db.query(models.WorkflowJob).filter(models.WorkflowJob.id == job_id).first()
    if job is None:
        return None
    if job.status == WorkflowJobStatus.canceled.value:
        return job
    job.status = WorkflowJobStatus.completed.value
    job.finished_at = _now()
    job.error_message = None
    db.commit()
    db.refresh(job)
    return job


def mark_failed(
    db: Session,
    job_id: str,
    error_message: str,
) -> models.WorkflowJob | None:
    job = db.query(models.WorkflowJob).filter(models.WorkflowJob.id == job_id).first()
    if job is None:
        return None
    if job.status == WorkflowJobStatus.canceled.value:
        return job
    job.status = WorkflowJobStatus.failed.value
    job.finished_at = _now()
    job.error_message = error_message
    db.commit()
    db.refresh(job)
    return job


def mark_canceled(
    db: Session,
    job_id: str,
    error_message: str | None = "Stopped by user",
) -> models.WorkflowJob | None:
    job = db.query(models.WorkflowJob).filter(models.WorkflowJob.id == job_id).first()
    if job is None:
        return None
    job.status = WorkflowJobStatus.canceled.value
    job.finished_at = _now()
    job.error_message = error_message
    db.commit()
    db.refresh(job)
    return job


def cancel_active_job(
    db: Session,
    project_id: str,
    error_message: str | None = "Stopped by user",
) -> models.WorkflowJob | None:
    job = get_active_job(db, project_id)
    if job is None:
        return None
    return mark_canceled(db, job.id, error_message)


def is_job_canceled(db: Session, job_id: str | None) -> bool:
    if not job_id:
        return False
    job = db.query(models.WorkflowJob.status).filter(models.WorkflowJob.id == job_id).first()
    return bool(job and job[0] == WorkflowJobStatus.canceled.value)


def list_project_jobs(db: Session, project_id: str) -> list[models.WorkflowJob]:
    return (
        db.query(models.WorkflowJob)
        .filter(models.WorkflowJob.project_id == project_id)
        .order_by(models.WorkflowJob.created_at.desc())
        .all()
    )


def serialize_job(job: models.WorkflowJob) -> WorkflowJobResponse:
    return WorkflowJobResponse(
        job_id=job.id,
        project_id=job.project_id,
        status=WorkflowJobStatus(job.status),
        backend=job.backend,
        attempts=int(job.attempts or 0),
        created_at=_iso(job.created_at),
        started_at=_iso(job.started_at) if job.started_at else None,
        finished_at=_iso(job.finished_at) if job.finished_at else None,
        error_message=job.error_message,
    )


def _iso(value) -> str:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc).isoformat()
    return str(value) if value is not None else ""
