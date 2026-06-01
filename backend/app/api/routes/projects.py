"""Project management routes.

Implements POST /api/projects, POST /api/projects/{id}/run, and
GET /api/projects/{id}. Workflow execution is delegated to the
LangGraph workflow when available.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.config import settings
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.schemas.competitor import CompetitorInput
from app.schemas.project import (
    ProjectCreate,
    ProjectResponse,
    ProjectStatus,
)
from app.services import project_service

# The graph workflow lives in a sibling package implemented by the agent
# workflow engineer. Import lazily so this module loads even before the
# workflow module exists.
try:  # pragma: no cover - tested via integration with graph package
    from app.graph.workflow import run_workflow_background  # type: ignore
except ImportError:  # pragma: no cover - fallback for partial scaffold
    run_workflow_background = None  # type: ignore[assignment]

logger = get_logger(__name__)

router = APIRouter()


def _to_response(project) -> ProjectResponse:
    return ProjectResponse(
        project_id=project.id,
        industry=project.industry,
        goals=project_service.deserialize_goals(project),
        status=ProjectStatus(project.status),
        output_language=project.output_language,
        created_at=_iso(project.created_at),
        updated_at=_iso(project.updated_at),
    )


def _iso(value) -> str:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc).isoformat()
    return str(value) if value is not None else ""


@router.post("/projects")
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_session),
) -> dict:
    """Create a project and return its identifier and initial status."""
    project = project_service.create_project(db, payload)
    return {
        "project_id": project.id,
        "status": project.status,
    }


@router.post("/projects/{project_id}/run")
def run_project(
    project_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
) -> dict:
    """Mark the project as running and trigger the workflow background task."""
    project = project_service.get_project(db, project_id)
    if project is None:
        raise NotFoundError("Project", project_id)

    project_service.update_project_status(db, project_id, ProjectStatus.running)

    competitors_payload: list[dict] = [
        CompetitorInput(name=c.name, url=c.url).model_dump()
        for c in project_service.get_project_competitors(db, project_id)
    ]
    goals_payload = project_service.deserialize_goals(project)

    if run_workflow_background is not None:
        background_tasks.add_task(
            run_workflow_background,
            project_id,
            competitors_payload,
            goals_payload,
            settings.database_url,
            project.output_language,
        )
    else:
        logger.warning(
            "Workflow background runner not available; project %s "
            "remains in 'running' state with no scheduled work.",
            project_id,
        )

    return {
        "project_id": project_id,
        "status": ProjectStatus.running.value,
    }


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    db: Session = Depends(get_session),
) -> ProjectResponse:
    project = project_service.get_project(db, project_id)
    if project is None:
        raise NotFoundError("Project", project_id)
    return _to_response(project)


@router.get("/projects", response_model=list[ProjectResponse])
def list_projects(db: Session = Depends(get_session)) -> list[ProjectResponse]:
    projects = project_service.list_projects(db)
    return [_to_response(p) for p in projects]
