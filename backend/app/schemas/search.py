"""Search candidate schemas for M15A interactive source search.

CandidateSource represents a Tavily result shown to the user for selection.
It is NOT evidence — it becomes evidence only after the user selects the URL
and CrawlerService successfully crawls the page.

CandidateSource.snippet is display-only and MUST NEVER be stored as
SourceEvidence.content or forwarded to any downstream agent.
"""

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.source import SourceType


class CandidateSource(BaseModel):
    candidate_id: str = Field(default_factory=lambda: f"cand_{uuid.uuid4().hex[:10]}")
    competitor_name: str
    url: str
    title: str
    snippet: str = ""
    suggested_source_type: SourceType = SourceType.unknown
    discovery_query: str = ""
    provider: str = "tavily"
    confidence: Literal["high", "medium", "low"] = "medium"
    reason: str = ""
    selected_by_default: bool = False
