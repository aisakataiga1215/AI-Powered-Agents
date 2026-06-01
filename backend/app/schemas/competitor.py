"""Competitor schema.

A competitor represents a product or company being analyzed in a
project. The :class:`CompetitorInput` form is used to accept user input
when creating a project.
"""

import uuid

from pydantic import BaseModel, Field


class CompetitorInput(BaseModel):
    name: str
    url: str


class Competitor(BaseModel):
    competitor_id: str = Field(default_factory=lambda: f"comp_{uuid.uuid4().hex[:8]}")
    name: str
    website: str
    description: str = ""
    metadata: dict = Field(default_factory=dict)
