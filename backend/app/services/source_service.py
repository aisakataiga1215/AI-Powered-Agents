"""Source service.

Persists collected :class:`SourceEvidence` rows and exposes lookup
helpers used by both the API layer and downstream agents.

Source identity rules:
- The DB primary key (``Source.id``) is always a freshly minted UUID so
  re-running the same workflow (or running multiple projects that share
  fixture data) never collides on the UNIQUE constraint.
- The original upstream identifier (e.g. the fixture's ``src_cursor_001``)
  is preserved as ``external_id`` for traceability.
- The in-memory :class:`SourceEvidence.source_id` is rewritten to the
  new UUID in place. This is intentional: downstream agents (Analyst,
  Writer, QA) reference sources by ``source_id``, so they must observe
  the same canonical id that lives in the database.
"""

import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db import models
from app.schemas.source import SourceEvidence

logger = get_logger(__name__)


def _mint_source_id() -> str:
    return f"src_{uuid.uuid4().hex[:12]}"


def save_sources(
    db: Session,
    project_id: str,
    sources: list[SourceEvidence],
) -> list[models.Source]:
    """Insert a batch of source evidence rows for a project.

    Mutates each ``SourceEvidence.source_id`` in place to the new UUID
    so callers can continue to use the same object reference downstream.
    Rolls back on any commit failure to keep the session usable.
    """
    if not sources:
        return []

    records: list[models.Source] = []
    for source in sources:
        external_id = source.source_id or None
        new_id = _mint_source_id()
        # Mutate in-place so downstream agents see the canonical id.
        source.source_id = new_id
        record = models.Source(
            id=new_id,
            external_id=external_id,
            project_id=project_id,
            competitor_id=source.competitor_id or "",
            competitor_name=source.competitor_name,
            source_type=source.source_type.value,
            url=source.url,
            title=source.title,
            snippet=source.snippet,
            content=source.content,
            retrieved_at=source.retrieved_at,
            reliability=source.reliability.value,
            data_source=source.data_source,
        )
        db.add(record)
        records.append(record)

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error(
            "save_sources commit failed for project %s: %s", project_id, exc
        )
        raise

    for record in records:
        db.refresh(record)
    return records


def get_source(db: Session, source_id: str) -> models.Source | None:
    return (
        db.query(models.Source)
        .filter(models.Source.id == source_id)
        .first()
    )


def get_project_sources(db: Session, project_id: str) -> list[models.Source]:
    return (
        db.query(models.Source)
        .filter(models.Source.project_id == project_id)
        .order_by(models.Source.retrieved_at.desc())
        .all()
    )
