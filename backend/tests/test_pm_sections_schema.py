"""Tests for pm_sections Pydantic schemas (M13B)."""

import pytest
from pydantic import ValidationError

from app.schemas.pm_sections import (
    FeatureInsights,
    GtmProfile,
    MarketBackground,
    MarketTrend,
    OperationMonetization,
)


def test_market_background_validates_all_fields():
    mb = MarketBackground(
        market_overview="A growing market driven by AI adoption.",
        market_size_notes="TAM estimated at $10B by 2026.",
        trends=[MarketTrend(trend="AI-first tools growing", evidence=["src_001"])],
        key_drivers=["Productivity demand", "Remote work"],
        key_challenges=["Data privacy", "High switching costs"],
    )
    assert mb.market_overview.startswith("A growing")
    assert len(mb.trends) == 1
    assert mb.trends[0].evidence == ["src_001"]


def test_market_background_empty_defaults():
    mb = MarketBackground()
    assert mb.market_overview == ""
    assert mb.market_size_notes == ""
    assert mb.trends == []
    assert mb.key_drivers == []
    assert mb.key_challenges == []


def test_feature_insights_differentiators_accept_dicts():
    fi = FeatureInsights(
        table_stakes=["Code completion", "Syntax highlighting"],
        differentiators=[{"feature": "AI chat", "competitors": ["Cursor", "Copilot"]}],
        gaps=["Offline mode"],
        cross_competitor_patterns=["All tools offer free tier"],
    )
    assert fi.differentiators[0]["feature"] == "AI chat"
    assert "Cursor" in fi.differentiators[0]["competitors"]


def test_gtm_profile_requires_competitor_name():
    with pytest.raises(ValidationError):
        GtmProfile()  # missing competitor_name


def test_operation_monetization_aarrr_notes_accepts_nested_dict():
    om = OperationMonetization(
        gtm_profiles=[GtmProfile(competitor_name="Cursor", motion="PLG")],
        monetization_patterns=["All tools use freemium at entry"],
        aarrr_notes={
            "acquisition": {"Cursor": "SEO + product-led trial"},
            "retention": {"Cursor": "Daily usage through IDE integration"},
        },
    )
    assert om.aarrr_notes["acquisition"]["Cursor"] == "SEO + product-led trial"
    assert len(om.gtm_profiles) == 1
