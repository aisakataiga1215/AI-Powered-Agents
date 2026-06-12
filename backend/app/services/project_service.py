"""Project service.

Owns project lifecycle persistence: creation with nested competitors,
status updates, retrieval, and listing. Business logic that touches the
project table belongs here, not in route handlers.
"""

import json
import uuid
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.db import models
from app.schemas.project import (
    ProjectCreate,
    ProjectStatus,
    normalize_analysis_frameworks,
    normalize_analysis_purpose,
)


def _competitor_identity(name: str, url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    normalized_url = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path.rstrip('/')}"
    return name.strip().lower(), normalized_url


def create_project(db: Session, data: ProjectCreate) -> models.Project:
    """Create a new project and its competitor rows in a single transaction."""
    project_id = f"proj_{uuid.uuid4().hex[:12]}"
    project = models.Project(
        id=project_id,
        industry=data.industry,
        goals=json.dumps(data.goals),
        status=ProjectStatus.created.value,
        output_language=data.output_language,
        report_depth=data.report_depth,
        data_mode=data.data_mode,
        industry_type=getattr(data, "industry_type", "general") or "general",
        analysis_purpose=normalize_analysis_purpose(getattr(data, "analysis_purpose", None)),
        analysis_frameworks=json.dumps(
            normalize_analysis_frameworks(getattr(data, "analysis_frameworks", None))
        ),
        custom_dimensions=json.dumps(getattr(data, "custom_dimensions", []) or []),
        research_inputs=json.dumps(
            [
                item.model_dump()
                for item in (getattr(data, "research_inputs", []) or [])
            ]
        ),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(project)

    seen_competitors: set[tuple[str, str]] = set()
    for competitor_input in data.competitors:
        identity = _competitor_identity(competitor_input.name, competitor_input.url)
        if identity in seen_competitors:
            continue
        seen_competitors.add(identity)
        competitor = models.Competitor(
            id=f"comp_{uuid.uuid4().hex[:12]}",
            project_id=project_id,
            name=competitor_input.name,
            url=competitor_input.url,
            description="",
            role=getattr(competitor_input, "role", "direct_competitor") or "direct_competitor",
            extra_urls=json.dumps(getattr(competitor_input, "extra_urls", []) or []),
        )
        db.add(competitor)

    db.commit()
    db.refresh(project)
    return project


def get_project(db: Session, project_id: str) -> models.Project | None:
    return (
        db.query(models.Project)
        .filter(models.Project.id == project_id)
        .first()
    )


def update_project_status(
    db: Session,
    project_id: str,
    status: ProjectStatus,
) -> models.Project | None:
    project = get_project(db, project_id)
    if project is None:
        return None
    project.status = status.value
    project.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(project)
    return project


def list_projects(db: Session) -> list[models.Project]:
    return (
        db.query(models.Project)
        .order_by(models.Project.created_at.desc())
        .all()
    )


def get_project_competitors(
    db: Session,
    project_id: str,
) -> list[models.Competitor]:
    return (
        db.query(models.Competitor)
        .filter(models.Competitor.project_id == project_id)
        .all()
    )


def deserialize_goals(project: models.Project) -> list[str]:
    """Convert the stored JSON goals string back into a list."""
    try:
        value = json.loads(project.goals or "[]")
        if isinstance(value, list):
            return [str(item) for item in value]
        return []
    except json.JSONDecodeError:
        return []
