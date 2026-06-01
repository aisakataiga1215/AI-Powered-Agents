"""Loose LLM extraction schema for the AnalystAgent.

The LLM is asked to return one of these per competitor. All structured
values are flattened to plain strings and lists-of-strings so the model
does not need to understand Claim, FeatureCategory, PricingModel, etc.

``normalization_service.normalize()`` then converts a
:class:`RawCompetitorExtraction` into the strict
:class:`~app.schemas.knowledge.CompetitorKnowledge` expected by the rest
of the pipeline.

This two-stage approach isolates schema-mismatch failures (which would
previously crash structured-output parsing) to a single
deterministic conversion step rather than polluting the LLM call.
"""

from pydantic import BaseModel, Field

from app.schemas._coercion import StrList


class RawFeature(BaseModel):
    name: str
    category: str = "General"
    availability: str = "available"
    description: str = ""


class RawPricingPlan(BaseModel):
    name: str
    price: str
    billing_cycle: str = "monthly"
    features: StrList = Field(default_factory=list)


class RawUserPersona(BaseModel):
    name: str
    description: str = ""
    needs: StrList = Field(default_factory=list)
    pain_points: StrList = Field(default_factory=list)


class RawCompetitorExtraction(BaseModel):
    """Flat, LLM-friendly representation of one competitor.

    Every field that would be a ``Claim`` in the strict schema is here a
    plain ``str``. Every field that would be a ``list[Claim]`` is here a
    ``list[str]``. The normalizer applies evidence and confidence after
    the fact.
    """

    name: str
    website: str = ""
    company: str = ""
    positioning: str = ""
    target_users: StrList = Field(default_factory=list)
    features: list[RawFeature] = Field(default_factory=list)
    has_free_plan: bool = False
    pricing_url: str = ""
    pricing_plans: list[RawPricingPlan] = Field(default_factory=list)
    pricing_summary: str = ""
    user_personas: list[RawUserPersona] = Field(default_factory=list)
    positive_points: StrList = Field(default_factory=list)
    negative_points: StrList = Field(default_factory=list)
    user_feedback_summary: str = ""
    strengths: StrList = Field(default_factory=list)
    weaknesses: StrList = Field(default_factory=list)
    opportunities: StrList = Field(default_factory=list)
    threats: StrList = Field(default_factory=list)
