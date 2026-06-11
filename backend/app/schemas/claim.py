"""Claim schema.

A claim is a single analytical statement that may appear in the final
report. Claims must either carry source evidence or be explicitly marked
as a hypothesis.
"""

import uuid
from enum import Enum

from pydantic import BaseModel, Field

from app.schemas._coercion import StrList


class ConfidenceLevel(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class Claim(BaseModel):
    claim_id: str = Field(default_factory=lambda: f"claim_{uuid.uuid4().hex[:8]}")
    text: str
    confidence: ConfidenceLevel = ConfidenceLevel.medium
    evidence: StrList = Field(default_factory=list)  # list of source_ids
    is_hypothesis: bool = False
    created_by: str = "AnalystAgent"
