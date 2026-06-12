"""Project management routes.

Implements POST /api/projects, POST /api/projects/{id}/run, and
GET /api/projects/{id}. Workflow execution is delegated to the
LangGraph workflow when available.
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.schemas.competitor import CompetitorInput
from app.schemas.project import (
    CompetitorInProject,
    ProjectCreate,
    ProjectResponse,
    ProjectStatus,
    normalize_analysis_frameworks,
    normalize_analysis_purpose,
)
from app.services import project_service, workflow_job_service

# The graph workflow lives in a sibling package implemented by the agent
# workflow engineer. Import lazily so this module loads even before the
# workflow module exists.
try:  # pragma: no cover - tested via integration with graph package
    from app.graph.workflow import run_workflow_background  # type: ignore
except ImportError:  # pragma: no cover - fallback for partial scaffold
    run_workflow_background = None  # type: ignore[assignment]

logger = get_logger(__name__)

router = APIRouter()


def _loads_list(value) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
        return []
    except (TypeError, json.JSONDecodeError):
        return []


def _to_response(project) -> ProjectResponse:
    return ProjectResponse(
        project_id=project.id,
        industry=project.industry,
        industry_type=getattr(project, "industry_type", "general") or "general",
        analysis_purpose=normalize_analysis_purpose(getattr(project, "analysis_purpose", None)),
        analysis_frameworks=normalize_analysis_frameworks(
            json.loads(getattr(project, "analysis_frameworks", '["swot"]') or '["swot"]')
        ),
        custom_dimensions=json.loads(getattr(project, "custom_dimensions", "[]") or "[]"),
        research_inputs=json.loads(getattr(project, "research_inputs", "[]") or "[]"),
        goals=project_service.deserialize_goals(project),
        status=ProjectStatus(project.status),
        output_language=project.output_language,
        created_at=_iso(project.created_at),
        updated_at=_iso(project.updated_at),
        data_mode=getattr(project, "data_mode", "demo") or "demo",
        competitors=[
            CompetitorInProject(
                name=c.name,
                url=c.url,
                role=getattr(c, "role", "direct_competitor") or "direct_competitor",
                extra_urls=_loads_list(getattr(c, "extra_urls", "[]")),
            )
            for c in (project.competitors or [])
        ],
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
    """Create a workflow job and schedule execution.

    Local development still uses FastAPI BackgroundTasks as the execution
    adapter. The durable job row and project-level active-job lock are the
    production contract; a Redis/Celery worker can consume the same payload.
    """
    project = project_service.get_project(db, project_id)
    if project is None:
        raise NotFoundError("Project", project_id)

    active_job = workflow_job_service.get_active_job(db, project_id)
    if active_job is not None:
        raise ConflictError(
            f"Project '{project_id}' already has active workflow job {active_job.id}"
        )

    competitors_payload: list[dict] = [
        {
            "name": c.name,
            "url": c.url,
            "role": getattr(c, "role", "direct_competitor") or "direct_competitor",
            "extra_urls": _loads_list(getattr(c, "extra_urls", "[]")),
        }
        for c in project_service.get_project_competitors(db, project_id)
    ]
    goals_payload = project_service.deserialize_goals(project)
    analysis_frameworks = normalize_analysis_frameworks(
        json.loads(getattr(project, "analysis_frameworks", '["swot"]') or '["swot"]')
    )
    custom_dimensions = json.loads(getattr(project, "custom_dimensions", "[]") or "[]")
    research_inputs = json.loads(getattr(project, "research_inputs", "[]") or "[]")

    job_payload = {
        "project_id": project_id,
        "competitors": competitors_payload,
        "goals": goals_payload,
        "analysis_frameworks": analysis_frameworks,
        "database_url": settings.database_url,
        "output_language": project.output_language,
        "data_mode": getattr(project, "data_mode", "demo") or "demo",
        "industry_type": getattr(project, "industry_type", "general") or "general",
        "analysis_purpose": normalize_analysis_purpose(
            getattr(project, "analysis_purpose", None)
        ),
        "custom_dimensions": custom_dimensions,
        "research_inputs": research_inputs,
    }
    job = workflow_job_service.create_job(
        db,
        project_id=project_id,
        payload=job_payload,
        backend="background_tasks",
    )
    project_service.update_project_status(db, project_id, ProjectStatus.running)

    if run_workflow_background is not None:
        background_tasks.add_task(
            run_workflow_job_background,
            job.id,
            job_payload,
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
        "job_id": job.id,
    }


def run_workflow_job_background(job_id: str, payload: dict) -> None:
    """BackgroundTasks adapter for a durable workflow job."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        workflow_job_service.mark_running(db, job_id)
    finally:
        db.close()

    try:
        run_workflow_background(
            payload["project_id"],
            payload["competitors"],
            payload["goals"],
            payload["analysis_frameworks"],
            payload["database_url"],
            payload["output_language"],
            payload["data_mode"],
            payload["industry_type"],
            payload["analysis_purpose"],
            payload["custom_dimensions"],
            payload["research_inputs"],
        )
    except Exception as exc:  # noqa: BLE001
        db = SessionLocal()
        try:
            workflow_job_service.mark_failed(db, job_id, str(exc))
        finally:
            db.close()
        raise
    else:
        db = SessionLocal()
        try:
            workflow_job_service.mark_completed(db, job_id)
        finally:
            db.close()


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


@router.get("/projects/{project_id}/jobs")
def list_project_jobs(
    project_id: str,
    db: Session = Depends(get_session),
) -> list[dict]:
    project = project_service.get_project(db, project_id)
    if project is None:
        raise NotFoundError("Project", project_id)
    return [
        workflow_job_service.serialize_job(job).model_dump(mode="json")
        for job in workflow_job_service.list_project_jobs(db, project_id)
    ]
