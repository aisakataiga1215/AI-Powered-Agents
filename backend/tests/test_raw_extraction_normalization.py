"""Tests for the two-stage AnalystAgent extraction pipeline.

Covers:
- _make_claim: str → Claim wrapping, empty-string handling
- _make_claims: list[str] → list[Claim]
- normalize: individual field conversions
  - target_users list[str] → list[Claim]
  - pricing_summary str → Claim
  - user_feedback_summary str → UserFeedbackSummary
  - swot str lists → list[Claim] per quadrant
  - features grouped by category → list[FeatureCategory]
  - availability normalization
- normalize: full round-trip with Cursor-like fixture
- normalize: gracefully handles empty strings / empty lists
- RawCompetitorExtraction: resilient to LLM string-instead-of-list quirks
  (StrList coercion)
"""

import pytest

from app.schemas.claim import ConfidenceLevel
from app.schemas.raw_extraction import (
    RawCompetitorExtraction,
    RawFeature,
    RawPricingPlan,
    RawUserPersona,
)
from app.services.normalization_service import (
    _availability,
    _make_claim,
    _make_claims,
    normalize,
)


# ---------------------------------------------------------------------------
# _make_claim
# ---------------------------------------------------------------------------


def test_make_claim_wraps_non_empty_text():
    claim = _make_claim("Market leader", ["src_1"])
    assert claim is not None
    assert claim.text == "Market leader"
    assert claim.evidence == ["src_1"]
    assert claim.is_hypothesis is False
    assert claim.created_by == "AnalystAgent"


def test_make_claim_returns_none_for_empty_string():
    assert _make_claim("", ["src_1"]) is None
    assert _make_claim("   ", ["src_1"]) is None


def test_make_claim_is_hypothesis_when_no_sources():
    claim = _make_claim("Might be strong", [])
    assert claim is not None
    assert claim.is_hypothesis is True
    assert claim.evidence == []


def test_make_claim_respects_confidence():
    claim = _make_claim("High confidence", ["src_1"], ConfidenceLevel.high)
    assert claim.confidence is ConfidenceLevel.high


# ---------------------------------------------------------------------------
# _make_claims
# ---------------------------------------------------------------------------


def test_make_claims_converts_list_of_strings():
    claims = _make_claims(["Strong UX", "Fast completions"], ["src_1", "src_2"])
    assert len(claims) == 2
    assert claims[0].text == "Strong UX"
    assert claims[1].text == "Fast completions"
    assert all(c.evidence == ["src_1", "src_2"] for c in claims)


def test_make_claims_filters_empty_strings():
    claims = _make_claims(["Good", "", "  ", "Fast"], ["src_1"])
    assert len(claims) == 2
    assert [c.text for c in claims] == ["Good", "Fast"]


def test_make_claims_empty_input():
    assert _make_claims([], ["src_1"]) == []
    assert _make_claims(None, ["src_1"]) == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _availability
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("available", "available"),
        ("Available", "available"),
        ("yes", "available"),
        ("true", "available"),
        ("limited", "limited"),
        ("partial", "limited"),
        ("no", "unknown"),
        ("false", "unknown"),
        ("unknown", "unknown"),
        ("n/a", "unknown"),
        ("anything_else", "available"),  # unknown input defaults to available
    ],
)
def test_availability_normalization(raw, expected):
    assert _availability(raw) == expected


# ---------------------------------------------------------------------------
# normalize: individual field conversions
# ---------------------------------------------------------------------------


def test_normalize_target_users_list_str_to_list_claim():
    raw = RawCompetitorExtraction(
        name="Cursor",
        target_users=["Solo developers", "Enterprise teams"],
    )
    ck = normalize(raw, ["src_1"])
    assert ck.product_profile is not None
    users = ck.product_profile.target_users
    assert len(users) == 2
    assert users[0].text == "Solo developers"
    assert users[1].text == "Enterprise teams"
    assert all(u.evidence == ["src_1"] for u in users)


def test_normalize_positioning_str_to_claim():
    raw = RawCompetitorExtraction(
        name="Cursor",
        positioning="AI-first code editor",
    )
    ck = normalize(raw, ["src_1"])
    assert ck.product_profile.positioning is not None
    assert ck.product_profile.positioning.text == "AI-first code editor"
    assert ck.product_profile.positioning.is_hypothesis is False


def test_normalize_empty_positioning_produces_none():
    raw = RawCompetitorExtraction(name="Cursor", positioning="")
    ck = normalize(raw, ["src_1"])
    assert ck.product_profile.positioning is None


def test_normalize_pricing_summary_str_to_claim():
    raw = RawCompetitorExtraction(
        name="Cursor",
        pricing_summary="Freemium with Pro at $20/mo",
    )
    ck = normalize(raw, ["src_pricing_01"])
    assert ck.pricing_model is not None
    assert ck.pricing_model.summary is not None
    assert ck.pricing_model.summary.text == "Freemium with Pro at $20/mo"
    assert ck.pricing_model.summary.evidence == ["src_pricing_01"]


def test_normalize_empty_pricing_summary_produces_none_summary():
    raw = RawCompetitorExtraction(name="Cursor", pricing_summary="")
    ck = normalize(raw, ["src_1"])
    assert ck.pricing_model.summary is None


def test_normalize_user_feedback_summary_str_builds_summary_object():
    raw = RawCompetitorExtraction(
        name="Cursor",
        positive_points=["Fast completions"],
        negative_points=["Privacy concerns"],
        user_feedback_summary="Mixed but mostly positive",
    )
    ck = normalize(raw, ["src_1"])
    assert ck.user_feedback_summary is not None
    assert len(ck.user_feedback_summary.positive_points) == 1
    assert ck.user_feedback_summary.positive_points[0].text == "Fast completions"
    assert len(ck.user_feedback_summary.negative_points) == 1
    assert ck.user_feedback_summary.negative_points[0].text == "Privacy concerns"
    assert ck.user_feedback_summary.summary == "Mixed but mostly positive"


def test_normalize_user_feedback_summary_str_only():
    """A plain string summary without bullet points is still preserved."""
    raw = RawCompetitorExtraction(
        name="Cursor",
        user_feedback_summary="Developers love it",
    )
    ck = normalize(raw, ["src_1"])
    assert ck.user_feedback_summary is not None
    assert ck.user_feedback_summary.summary == "Developers love it"
    assert ck.user_feedback_summary.positive_points == []
    assert ck.user_feedback_summary.negative_points == []


def test_normalize_no_feedback_produces_none():
    raw = RawCompetitorExtraction(name="Cursor")
    ck = normalize(raw, ["src_1"])
    assert ck.user_feedback_summary is None


def test_normalize_swot_strings_to_claims():
    raw = RawCompetitorExtraction(
        name="Cursor",
        strengths=["Strong AI", "Good UX"],
        weaknesses=["Pricey"],
        opportunities=["Enterprise expansion"],
        threats=["GitHub Copilot"],
    )
    ck = normalize(raw, ["src_1"])
    assert ck.swot is not None
    assert len(ck.swot.strengths) == 2
    assert ck.swot.strengths[0].text == "Strong AI"
    assert len(ck.swot.weaknesses) == 1
    assert len(ck.swot.opportunities) == 1
    assert len(ck.swot.threats) == 1
    assert all(c.evidence == ["src_1"] for c in ck.swot.strengths)


# ---------------------------------------------------------------------------
# normalize: feature grouping
# ---------------------------------------------------------------------------


def test_normalize_features_grouped_by_category():
    raw = RawCompetitorExtraction(
        name="Cursor",
        features=[
            RawFeature(name="Tab completion", category="AI Coding"),
            RawFeature(name="Chat", category="AI Chat"),
            RawFeature(name="Codebase context", category="AI Coding"),
        ],
    )
    ck = normalize(raw, ["src_1"])
    assert len(ck.feature_tree) == 2
    categories = {cat.category: cat for cat in ck.feature_tree}
    assert "AI Coding" in categories
    assert len(categories["AI Coding"].features) == 2
    assert "AI Chat" in categories
    assert len(categories["AI Chat"].features) == 1


def test_normalize_features_availability_mapped():
    raw = RawCompetitorExtraction(
        name="Cursor",
        features=[
            RawFeature(name="A", availability="yes"),
            RawFeature(name="B", availability="partial"),
            RawFeature(name="C", availability="no"),
        ],
    )
    ck = normalize(raw, ["src_1"])
    avs = {f.name: f.availability for cat in ck.feature_tree for f in cat.features}
    assert avs["A"] == "available"
    assert avs["B"] == "limited"
    assert avs["C"] == "unknown"


def test_normalize_empty_features_produces_empty_tree():
    raw = RawCompetitorExtraction(name="Cursor")
    ck = normalize(raw, ["src_1"])
    assert ck.feature_tree == []


# ---------------------------------------------------------------------------
# normalize: pricing plans
# ---------------------------------------------------------------------------


def test_normalize_pricing_plans_to_pydantic():
    raw = RawCompetitorExtraction(
        name="Cursor",
        has_free_plan=True,
        pricing_url="https://cursor.com/pricing",
        pricing_plans=[
            RawPricingPlan(name="Hobby", price="free"),
            RawPricingPlan(name="Pro", price="$20", billing_cycle="monthly"),
        ],
    )
    ck = normalize(raw, ["src_pricing_01"])
    pm = ck.pricing_model
    assert pm.has_free_plan is True
    assert pm.pricing_url == "https://cursor.com/pricing"
    assert len(pm.plans) == 2
    assert pm.plans[1].price == "$20"
    assert pm.plans[1].evidence == ["src_pricing_01"]


# ---------------------------------------------------------------------------
# normalize: full round-trip — Cursor-shaped fixture
# ---------------------------------------------------------------------------


def test_normalize_full_cursor_extraction():
    raw = RawCompetitorExtraction(
        name="Cursor",
        website="https://cursor.com",
        company="Anysphere",
        positioning="AI-first code editor for professional developers",
        target_users=["Professional software engineers", "Students"],
        features=[
            RawFeature(name="Tab completion", category="AI Coding", availability="available"),
            RawFeature(name="Codebase chat", category="AI Chat", availability="available"),
        ],
        has_free_plan=True,
        pricing_url="https://cursor.com/pricing",
        pricing_plans=[
            RawPricingPlan(name="Hobby", price="free"),
            RawPricingPlan(name="Pro", price="$20"),
        ],
        pricing_summary="Freemium with Pro at $20/month",
        positive_points=["Fast completions", "Deep codebase context"],
        negative_points=["Privacy concerns for enterprise"],
        user_feedback_summary="Widely praised for AI quality",
        strengths=["Market leader", "Strong VC backing"],
        weaknesses=["Expensive for individuals"],
        opportunities=["Enterprise adoption"],
        threats=["GitHub Copilot competition"],
    )
    source_ids = ["src_cursor_001", "src_cursor_002"]
    ck = normalize(raw, source_ids)

    assert ck.competitor_name == "Cursor"
    assert ck.product_profile.name == "Cursor"
    assert ck.product_profile.website == "https://cursor.com"
    assert ck.product_profile.positioning.text == "AI-first code editor for professional developers"
    assert len(ck.product_profile.target_users) == 2

    assert len(ck.feature_tree) == 2
    assert ck.pricing_model.has_free_plan is True
    assert len(ck.pricing_model.plans) == 2
    assert ck.pricing_model.summary.text == "Freemium with Pro at $20/month"

    assert ck.user_feedback_summary is not None
    assert len(ck.user_feedback_summary.positive_points) == 2
    assert len(ck.user_feedback_summary.negative_points) == 1

    assert len(ck.swot.strengths) == 2
    assert len(ck.swot.weaknesses) == 1

    assert ck.sources == source_ids
    assert all(
        c.evidence == source_ids
        for c in ck.swot.strengths + ck.swot.weaknesses
    )


# ---------------------------------------------------------------------------
# RawCompetitorExtraction: StrList coercion catches LLM str quirks
# ---------------------------------------------------------------------------


def test_raw_target_users_coerces_single_string():
    """LLM returning a string instead of a list must be wrapped, not fail."""
    raw = RawCompetitorExtraction(
        name="Cursor",
        target_users="Professional software engineers",  # type: ignore[arg-type]
    )
    assert raw.target_users == ["Professional software engineers"]


def test_raw_strengths_coerces_single_string():
    raw = RawCompetitorExtraction(
        name="Cursor",
        strengths="Market leader",  # type: ignore[arg-type]
    )
    assert raw.strengths == ["Market leader"]


def test_raw_none_list_fields_become_empty():
    raw = RawCompetitorExtraction(
        name="Cursor",
        target_users=None,  # type: ignore[arg-type]
        strengths=None,  # type: ignore[arg-type]
    )
    assert raw.target_users == []
    assert raw.strengths == []


# ---------------------------------------------------------------------------
# normalize: source_id binding
# ---------------------------------------------------------------------------


def test_normalize_binds_all_source_ids_to_claims():
    source_ids = ["src_a", "src_b", "src_c"]
    raw = RawCompetitorExtraction(
        name="Windsurf",
        positioning="Agentic IDE",
        strengths=["Strong Flows feature"],
    )
    ck = normalize(raw, source_ids)
    assert ck.product_profile.positioning.evidence == source_ids
    assert ck.swot.strengths[0].evidence == source_ids


def test_normalize_competitor_id_assigned_when_empty():
    raw = RawCompetitorExtraction(name="Trae")
    ck = normalize(raw, ["src_1"])
    assert ck.competitor_id.startswith("comp_")


def test_normalize_competitor_id_preserved_when_provided():
    raw = RawCompetitorExtraction(name="Trae")
    ck = normalize(raw, ["src_1"], competitor_id="comp_existing")
    assert ck.competitor_id == "comp_existing"


# user_personas fallback from target_users -----------------------------------


def test_normalize_derives_user_personas_from_target_users_when_none_provided():
    """When LLM returns no user_personas, normalize derives them from target_users."""
    raw = RawCompetitorExtraction(
        name="Cursor",
        target_users=["Professional software engineers", "Students learning to code"],
    )
    ck = normalize(raw, ["src_1"])
    assert len(ck.user_personas) == 2
    persona_names = [p.name for p in ck.user_personas]
    assert "Professional software engineers" in persona_names
    assert "Students learning to code" in persona_names


def test_normalize_does_not_override_explicit_user_personas():
    """When LLM explicitly provides user_personas, those are kept as-is."""
    raw = RawCompetitorExtraction(
        name="Cursor",
        target_users=["Solo devs"],
        user_personas=[
            RawUserPersona(
                name="Power User",
                description="Heavy IDE user",
                needs=["Speed", "Context"],
            )
        ],
    )
    ck = normalize(raw, ["src_1"])
    assert len(ck.user_personas) == 1
    assert ck.user_personas[0].name == "Power User"


def test_normalize_no_user_personas_when_no_target_users():
    """With neither user_personas nor target_users the list stays empty."""
    raw = RawCompetitorExtraction(name="Cursor")
    ck = normalize(raw, ["src_1"])
    assert ck.user_personas == []
