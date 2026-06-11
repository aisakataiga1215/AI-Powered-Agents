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
from app.schemas.agent_message import AgentMessage
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


def record_agent_message(
    db: Session,
    message: AgentMessage,
) -> models.AgentRun:
    """Persist a structured AgentMessage as an auditable trace event.

    Runtime payloads still flow through LangGraph state for execution, but
    every logical edge can now be inspected as a first-class structured
    message in the Trace timeline.
    """
    return save_agent_run(
        db,
        AgentRun(
            agent_run_id=message.message_id,
            project_id=message.project_id,
            agent_name="AgentMessage",
            input={
                "from_agent": message.from_agent,
                "to_agent": message.to_agent,
                "message_type": message.message_type.value,
            },
            output=message.model_dump(mode="json"),
            status=AgentRunStatus.success,
        ),
    )


def aggregate_costs(
    db: Session,
    project_id: str | None = None,
    since: datetime | None = None,
) -> dict:
    """Return token cost aggregates across agent runs.

    Filters by ``project_id`` and/or ``since`` when provided.
    Returns ``{total_cost_usd, by_agent, by_project, by_day}``.
    """
    query = db.query(models.AgentRun)
    if project_id:
        query = query.filter(models.AgentRun.project_id == project_id)
    if since:
        query = query.filter(models.AgentRun.created_at >= since)

    records = query.all()

    total_cost = 0.0
    total_tokens = 0
    by_agent: dict[str, dict[str, float | int]] = {}
    by_project: dict[str, dict[str, float | int]] = {}
    by_day: dict[str, dict[str, float | int]] = {}

    def add(bucket: dict[str, dict[str, float | int]], key: str, cost: float, tokens: int) -> None:
        current = bucket.setdefault(key, {"cost_usd": 0.0, "total_tokens": 0, "run_count": 0})
        current["cost_usd"] = float(current["cost_usd"]) + cost
        current["total_tokens"] = int(current["total_tokens"]) + tokens
        current["run_count"] = int(current["run_count"]) + 1

    for record in records:
        try:
            usage = json.loads(record.token_usage_json or "{}")
        except json.JSONDecodeError:
            usage = {}
        cost = float(usage.get("cost_usd") or 0.0)
        tokens = int(usage.get("total_tokens") or 0)
        total_cost += cost
        total_tokens += tokens

        agent = record.agent_name or "unknown"
        add(by_agent, agent, cost, tokens)

        proj = record.project_id or "unknown"
        add(by_project, proj, cost, tokens)

        ts = record.created_at
        if isinstance(ts, datetime):
            day = ts.date().isoformat()
        elif isinstance(ts, str):
            day = ts[:10]
        else:
            day = "unknown"
        add(by_day, day, cost, tokens)

    def rounded(bucket: dict[str, dict[str, float | int]]) -> dict[str, dict[str, float | int]]:
        return {
            key: {
                "cost_usd": round(float(value["cost_usd"]), 6),
                "total_tokens": int(value["total_tokens"]),
                "run_count": int(value["run_count"]),
            }
            for key, value in bucket.items()
        }

    return {
        "total_cost_usd": round(total_cost, 6),
        "total_tokens": total_tokens,
        "run_count": len(records),
        "by_agent": rounded(by_agent),
        "by_project": rounded(by_project),
        "by_day": rounded(dict(sorted(by_day.items()))),
    }


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
