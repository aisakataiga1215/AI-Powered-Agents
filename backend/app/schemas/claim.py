"""Claim schema.

A claim is a single analytical statement that may appear in the final
report. Claims must either carry source evidence or be explicitly marked
as a hypothesis.
"""

import uuid
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.schemas._coercion import StrList


class ConfidenceLevel(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class Sentence(BaseModel):
    """A single sentence of a claim carrying its own source list.

    Sentence-level citations let the report viewer attach footnotes per
    sentence instead of per claim. ``sources`` must be a subset of the
    bundle's known source ids; the writer agent enforces this before
    persisting the report.
    """

    text: str
    sources: StrList = Field(default_factory=list)


class Claim(BaseModel):
    claim_id: str = Field(default_factory=lambda: f"claim_{uuid.uuid4().hex[:8]}")
    text: str
    confidence: ConfidenceLevel = ConfidenceLevel.medium
    evidence: StrList = Field(default_factory=list)  # union of source_ids across sentences
    sentences: list[Sentence] | None = None
    is_hypothesis: bool = False
    created_by: str = "AnalystAgent"

    @model_validator(mode="after")
    def _sync_evidence_with_sentences(self) -> "Claim":
        """Keep ``evidence`` consistent with ``sentences`` when both are present.

        When ``sentences`` is supplied, ``evidence`` is the deduplicated
        union of every sentence's sources (preserving order). Callers can
        still pass legacy ``evidence`` alone — those paths leave
        ``sentences`` as ``None`` and behave as before.
        """
        if self.sentences:
            seen: set[str] = set()
            union: list[str] = []
            for sentence in self.sentences:
                for source_id in sentence.sources:
                    if source_id and source_id not in seen:
                        seen.add(source_id)
                        union.append(source_id)
            if union:
                self.evidence = union
        return self
