"""Report retrieval routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.errors import NotFoundError
from app.services import project_service, report_service

router = APIRouter()


@router.get("/projects/{project_id}/report")
def get_project_report(
    project_id: str,
    db: Session = Depends(get_session),
) -> dict:
    project = project_service.get_project(db, project_id)
    if project is None:
        raise NotFoundError("Project", project_id)
    record = report_service.get_report(db, project_id)
    if record is None:
        raise NotFoundError("Report", project_id)
    return report_service.serialize_report(record)
