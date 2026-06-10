"""Competitor schema.

A competitor represents a product or company being analyzed in a
project. The :class:`CompetitorInput` form is used to accept user input
when creating a project.
"""

import uuid
from typing import Literal

from pydantic import BaseModel, Field

CompetitorRole = Literal[
    "direct_competitor",
    "indirect_competitor",
    "inspiration_product",
    "benchmark_leader",
]


class CompetitorInput(BaseModel):
    name: str
    url: str
    role: CompetitorRole = "direct_competitor"
    extra_urls: list[str] = Field(default_factory=list)


class Competitor(BaseModel):
    competitor_id: str = Field(default_factory=lambda: f"comp_{uuid.uuid4().hex[:8]}")
    name: str
    website: str
    description: str = ""
    metadata: dict = Field(default_factory=dict)
