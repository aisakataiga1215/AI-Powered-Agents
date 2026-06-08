"""Trace inspection routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.errors import NotFoundError
from app.services import project_service, trace_service

router = APIRouter()


@router.get("/projects/{project_id}/traces")
def get_project_traces(
    project_id: str,
    db: Session = Depends(get_session),
) -> dict:
    project = project_service.get_project(db, project_id)
    if project is None:
        raise NotFoundError("Project", project_id)
    records = trace_service.get_project_traces(db, project_id)
    return {
        "project_id": project_id,
        "traces": [trace_service.serialize_agent_run(r) for r in records],
    }
