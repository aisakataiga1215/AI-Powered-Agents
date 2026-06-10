"""Trace service.

Persists :class:`AgentRun` records so the frontend trace timeline can
replay each agent execution.
"""

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db import models
from app.schemas.trace import AgentRun, AgentRunStatus, TokenUsage

logger = get_logger(__name__)


def _safe_commit(db: Session, action: str) -> None:
    """Commit, rolling back on failure so the session stays usable.

    Trace writes happen on both success and failure paths. A previous
    failed commit can leave the session dirty; without rollback the next
    write would raise ``PendingRollbackError`` and we'd lose the trace.
    """
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("trace_service %s commit failed: %s", action, exc)
        raise


def save_agent_run(db: Session, run: AgentRun) -> models.AgentRun:
    """Persist a new agent run record."""
    # Defensive: a prior node failure may have left the session dirty.
    if db.in_transaction() and db.dirty:
        db.rollback()
    record = models.AgentRun(
        id=run.agent_run_id,
        project_id=run.project_id,
        agent_name=run.agent_name,
        input_json=json.dumps(run.input, ensure_ascii=False),
        output_json=json.dumps(run.output, ensure_ascii=False),
        status=run.status.value,
        error_message=run.error_message,
        latency_ms=run.latency_ms,
        token_usage_json=json.dumps(run.token_usage.model_dump()),
        retry_count=run.retry_count,
        created_at=datetime.utcnow(),
    )
    db.add(record)
    _safe_commit(db, "save_agent_run")
    db.refresh(record)
    return record


def update_agent_run(
    db: Session,
    run_id: str,
    **updates: Any,
) -> models.AgentRun | None:
    """Update mutable fields on an existing agent run.

    Accepted updates: ``status``, ``output``, ``error_message``,
    ``latency_ms``, ``token_usage``, ``retry_count``.
    """
    # If the caller is recording a failure, an earlier op may have left
    # the session in a half-committed state. Rolling back first guarantees
    # the trace update itself can commit.
    try:
        record = (
            db.query(models.AgentRun)
            .filter(models.AgentRun.id == run_id)
            .first()
        )
    except SQLAlchemyError:
        db.rollback()
        record = (
            db.query(models.AgentRun)
            .filter(models.AgentRun.id == run_id)
            .first()
        )
    if record is None:
        return None

    if "status" in updates:
        status = updates["status"]
        record.status = (
            status.value if isinstance(status, AgentRunStatus) else str(status)
        )
    if "output" in updates:
        record.output_json = json.dumps(updates["output"], ensure_ascii=False)
    if "error_message" in updates:
        record.error_message = updates["error_message"]
    if "latency_ms" in updates:
        record.latency_ms = int(updates["latency_ms"])
    if "token_usage" in updates:
        token_usage = updates["token_usage"]
        if isinstance(token_usage, TokenUsage):
            record.token_usage_json = json.dumps(token_usage.model_dump())
        else:
            record.token_usage_json = json.dumps(dict(token_usage))
    if "retry_count" in updates:
        record.retry_count = int(updates["retry_count"])

    _safe_commit(db, "update_agent_run")
    db.refresh(record)
    return record


def get_project_traces(
    db: Session,
    project_id: str,
) -> list[models.AgentRun]:
    return (
        db.query(models.AgentRun)
        .filter(models.AgentRun.project_id == project_id)
        .order_by(models.AgentRun.created_at.asc())
        .all()
    )


def record_workflow_event(
    db: Session,
    project_id: str,
    event_name: str,
    input_payload: dict | None = None,
    output_payload: dict | None = None,
) -> models.AgentRun:
    run = AgentRun(
        project_id=project_id,
        agent_name="WorkflowRouter",
        input={"event_name": event_name, **(input_payload or {})},
        output=output_payload or {},
        status=AgentRunStatus.success,
    )
    return save_agent_run(db, run)


def serialize_agent_run(record: models.AgentRun) -> dict:
    """Serialize an :class:`AgentRun` ORM row into a JSON-friendly dict."""
    try:
        input_payload = json.loads(record.input_json or "{}")
    except json.JSONDecodeError:
        input_payload = {}
    try:
        output_payload = json.loads(record.output_json or "{}")
    except json.JSONDecodeError:
        output_payload = {}
    try:
        token_usage = json.loads(record.token_usage_json or "{}")
    except json.JSONDecodeError:
        token_usage = {}

    return {
        "agent_run_id": record.id,
        "project_id": record.project_id,
        "agent_name": record.agent_name,
        "input": input_payload,
        "output": output_payload,
        "status": record.status,
        "error_message": record.error_message,
        "latency_ms": record.latency_ms,
        "token_usage": token_usage,
        "retry_count": record.retry_count,
        "created_at": record.created_at.replace(tzinfo=timezone.utc).isoformat()
        if isinstance(record.created_at, datetime)
        else record.created_at,
    }
