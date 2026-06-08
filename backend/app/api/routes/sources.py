"""Source detail routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.errors import NotFoundError
from app.services import source_service

router = APIRouter()


@router.get("/sources/{source_id}")
def get_source(
    source_id: str,
    db: Session = Depends(get_session),
) -> dict:
    record = source_service.get_source(db, source_id)
    if record is None:
        raise NotFoundError("Source", source_id)
    return {
        "source_id": record.id,
        "project_id": record.project_id,
        "competitor_id": record.competitor_id,
        "competitor_name": record.competitor_name,
        "source_type": record.source_type,
        "url": record.url,
        "title": record.title,
        "snippet": record.snippet,
        "content": record.content,
        "retrieved_at": record.retrieved_at,
        "reliability": record.reliability,
        "data_source": getattr(record, "data_source", "demo") or "demo",
    }
