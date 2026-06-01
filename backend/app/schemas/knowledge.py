"""Structured competitor knowledge schema.

This module defines the structured knowledge object produced by the
AnalystAgent from the raw source evidence. It mirrors the contract in
``docs/schema_design.md``.
"""

from pydantic import BaseModel, Field

from app.schemas._coercion import StrList
from app.schemas.claim import Claim


class ProductProfile(BaseModel):
    name: str
    website: str
    company: str = ""
    positioning: Claim | None = None
    target_users: list[Claim] = Field(default_factory=list)


class FeatureItem(BaseModel):
    name: str
    description: str = ""
    availability: str = "unknown"  # "available" | "limited" | "unknown"
    evidence: StrList = Field(default_factory=list)  # source_ids


class FeatureCategory(BaseModel):
    category: str
    features: list[FeatureItem] = Field(default_factory=list)


class PricingPlan(BaseModel):
    name: str
    price: str
    currency: str = "USD"
    billing_cycle: str = "monthly"
    features: StrList = Field(default_factory=list)
    evidence: StrList = Field(default_factory=list)


class PricingModel(BaseModel):
    has_free_plan: bool = False
    pricing_url: str = ""
    plans: list[PricingPlan] = Field(default_factory=list)
    summary: Claim | None = None


class UserPersona(BaseModel):
    name: str
    description: str = ""
    needs: StrList = Field(default_factory=list)
    pain_points: StrList = Field(default_factory=list)
    evidence: StrList = Field(default_factory=list)


class UserFeedbackSummary(BaseModel):
    positive_points: list[Claim] = Field(default_factory=list)
    negative_points: list[Claim] = Field(default_factory=list)
    summary: str = ""


class SWOTAnalysis(BaseModel):
    strengths: list[Claim] = Field(default_factory=list)
    weaknesses: list[Claim] = Field(default_factory=list)
    opportunities: list[Claim] = Field(default_factory=list)
    threats: list[Claim] = Field(default_factory=list)


class CompetitorKnowledge(BaseModel):
    # ``competitor_id`` is backfilled by the AnalystAgent after the LLM
    # returns; keeping it optional means structured-output validation
    # succeeds even when the model omits this synthetic identifier.
    competitor_id: str = ""
    competitor_name: str = ""
    product_profile: ProductProfile | None = None
    feature_tree: list[FeatureCategory] = Field(default_factory=list)
    pricing_model: PricingModel | None = None
    user_personas: list[UserPersona] = Field(default_factory=list)
    user_feedback_summary: UserFeedbackSummary | None = None
    swot: SWOTAnalysis | None = None
    sources: StrList = Field(default_factory=list)
