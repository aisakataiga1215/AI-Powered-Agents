"""Source evidence schema.

Source evidence stores the original information collected from public
sources. Every important report claim should reference at least one
source by ``source_id``.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum

from typing import Literal

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    official_website = "official_website"
    pricing_page = "pricing_page"
    docs = "docs"
    features_page = "features_page"
    security = "security"
    privacy = "privacy"
    blog = "blog"
    review = "review"
    news = "news"
    manual_input = "manual_input"
    unknown = "unknown"


class Reliability(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class SourceEvidence(BaseModel):
    source_id: str = Field(default_factory=lambda: f"src_{uuid.uuid4().hex[:12]}")
    project_id: str = ""
    competitor_id: str = ""
    competitor_name: str
    source_type: SourceType
    url: str
    title: str
    snippet: str = ""
    content: str = ""
    retrieved_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reliability: Reliability = Reliability.medium
    data_source: Literal["live", "demo", "search", "manual"] = "demo"
