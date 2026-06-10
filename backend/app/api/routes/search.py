"""Interactive search routes — M15A: source search for known competitors.
M15B: competitor discovery from industry query.
"""

from fastapi import APIRouter
from pydantic import BaseModel, HttpUrl, field_validator

from app.core.config import settings
from app.schemas.search import CandidateSource
from app.services.search_provider import create_provider_from_settings
from app.services.search_service import SearchService

router = APIRouter()


class SourceSearchRequest(BaseModel):
    competitor_name: str
    website: HttpUrl
    goals: list[str] = []
    industry_type: str = "general"

    @field_validator("competitor_name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("competitor_name is required")
        return v.strip()


class CompetitorDiscoveryRequest(BaseModel):
    industry: str
    industry_type: str = "general"

    @field_validator("industry")
    @classmethod
    def industry_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("industry is required")
        return v.strip()


def _search_configured() -> bool:
    return bool(settings.enable_live_search and settings.tavily_api_key)


@router.get("/search/status")
def search_status() -> dict:
    """Expose whether live search is configured so the UI can choose sane defaults."""
    return {
        "search_available": _search_configured(),
    }


@router.post("/search/sources")
def search_sources(payload: SourceSearchRequest) -> dict:
    """Candidate source URLs for user selection. Snippet is discovery hint, not evidence."""
    svc = SearchService(create_provider_from_settings())
    candidates = svc.search_sources(
        payload.competitor_name,
        str(payload.website),
        payload.goals,
        payload.industry_type,
    )
    return {
        "candidates": [c.model_dump() for c in candidates],
        "search_available": _search_configured(),
    }


@router.post("/search/competitors")
def discover_competitors(payload: CompetitorDiscoveryRequest) -> dict:
    """Candidate competitors for user selection. Descriptions are display-only."""
    svc = SearchService(create_provider_from_settings())
    candidates = svc.discover_competitors(payload.industry, payload.industry_type)
    return {
        "candidates": [c.model_dump() for c in candidates],
        "search_available": _search_configured(),
    }
