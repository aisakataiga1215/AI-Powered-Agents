"""Purpose-specific PM report sections."""

from pydantic import BaseModel, Field


class MarketBackground(BaseModel):
    market_overview: str = ""
    key_trends: list[str] = Field(default_factory=list)
    growth_drivers: list[str] = Field(default_factory=list)
    market_challenges: list[str] = Field(default_factory=list)


class FeatureInsights(BaseModel):
    table_stakes: list[str] = Field(default_factory=list)
    differentiators: dict[str, list[str]] = Field(default_factory=dict)
    feature_gaps: list[str] = Field(default_factory=list)


class OperationMonetization(BaseModel):
    gtm_profiles: dict[str, str] = Field(default_factory=dict)
    monetization_patterns: list[str] = Field(default_factory=list)
    aarrr_notes: dict[str, list[str]] = Field(default_factory=dict)
