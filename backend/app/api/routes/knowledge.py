"""Manual knowledge correction routes.

Implements PATCH /api/projects/{project_id}/knowledge so a human
reviewer can override the AnalystAgent's structured output before the
final report is generated.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.errors import NotFoundError, ValidationError
from app.db import models
from app.schemas.knowledge import CompetitorKnowledge
from app.services import project_service

router = APIRouter()


@router.patch("/projects/{project_id}/knowledge")
def patch_project_knowledge(
    project_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_session),
) -> dict:
    """Upsert structured competitor knowledge for a project.

    Expects a payload of the form::

        {
          "competitor_knowledge": [
            {"competitor_id": "...", "product_profile": {...}, ...}
          ]
        }
    """
    project = project_service.get_project(db, project_id)
    if project is None:
        raise NotFoundError("Project", project_id)

    raw_records = payload.get("competitor_knowledge")
    if not isinstance(raw_records, list) or not raw_records:
        raise ValidationError(
            "Request body must include a non-empty "
            "'competitor_knowledge' array."
        )

    updated_ids: list[str] = []
    for raw in raw_records:
        try:
            knowledge = CompetitorKnowledge.model_validate(raw)
        except Exception as exc:  # noqa: BLE001 - surface schema errors
            raise ValidationError(
                f"Invalid CompetitorKnowledge payload: {exc}"
            ) from exc

        existing = (
            db.query(models.CompetitorKnowledgeRecord)
            .filter(
                models.CompetitorKnowledgeRecord.project_id == project_id,
                models.CompetitorKnowledgeRecord.competitor_id
                == knowledge.competitor_id,
            )
            .first()
        )

        knowledge_json = json.dumps(
            knowledge.model_dump(mode="json"),
            ensure_ascii=False,
        )

        if existing is None:
            record = models.CompetitorKnowledgeRecord(
                id=f"know_{uuid.uuid4().hex[:12]}",
                project_id=project_id,
                competitor_id=knowledge.competitor_id,
                knowledge_json=knowledge_json,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(record)
        else:
            existing.knowledge_json = knowledge_json
            existing.updated_at = datetime.now(timezone.utc)
        updated_ids.append(knowledge.competitor_id)

    db.commit()

    return {
        "project_id": project_id,
        "updated_competitor_ids": updated_ids,
    }
