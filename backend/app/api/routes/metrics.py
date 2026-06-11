"""Metrics routes for token and estimated cost observability."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.services import trace_service

router = APIRouter()


@router.get("/metrics")
def get_metrics(
    project_id: str | None = None,
    since: str | None = Query(default=None, description="ISO date/datetime"),
    db: Session = Depends(get_session),
) -> dict:
    since_dt: datetime | None = None
    if since:
        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
    return trace_service.aggregate_costs(db, project_id=project_id, since=since_dt)
