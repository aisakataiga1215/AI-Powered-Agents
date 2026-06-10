"""Discovery schemas — competitor candidate returned by SearchService.discover_competitors()."""

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class CandidateCompetitor(BaseModel):
    candidate_id: str = Field(default_factory=lambda: f"comp_{uuid.uuid4().hex[:10]}")
    name: str
    website: str
    description: str = ""              # Tavily snippet — display-only, never evidence
    # Provenance
    raw_title: str = ""                # original Tavily page title, unmodified
    source_url: str = ""               # original Tavily URL that produced this candidate
    domain: str = ""
    discovery_query: str = ""
    provider: str = "tavily"
    # Quality signals
    confidence: Literal["high", "medium", "low"] = "medium"
    relevance_score: int = 50          # 0-100; used for sorting and UI display
    relevance_reason: str = ""
    suggested_role: Literal[
        "direct_competitor",
        "indirect_competitor",
        "inspiration_product",
        "benchmark_leader",
    ] = "direct_competitor"
    role_confidence: Literal["high", "medium", "low"] = "medium"
    reason: str = ""
    selected_by_default: bool = False
