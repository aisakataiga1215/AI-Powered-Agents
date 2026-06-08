"""Tests for normalization_service.normalize() persona fallback quality."""

from app.services.normalization_service import normalize
from app.schemas.raw_extraction import RawCompetitorExtraction, RawUserPersona

PLACEHOLDER = "User segment identified from target audience analysis"


def _raw(name: str, target_users: list, positioning: str = "") -> RawCompetitorExtraction:
    return RawCompetitorExtraction(
        name=name,
        positioning=positioning,
        target_users=target_users,
    )


class TestFallbackPersonaDescription:
    def test_fallback_description_is_not_placeholder(self):
        raw = _raw("Cursor", ["Individual developers"])
        result = normalize(raw, source_ids=["src_001"])
        assert PLACEHOLDER not in result.user_personas[0].description

    def test_fallback_description_includes_product_name(self):
        raw = _raw("Windsurf", ["Professional developers"])
        result = normalize(raw, source_ids=["src_001"])
        assert len(result.user_personas) == 1
        assert "Windsurf" in result.user_personas[0].description

    def test_fallback_description_includes_positioning_hint_when_present(self):
        raw = _raw(
            "Cursor",
            ["Freelance developers"],
            positioning="AI-first code editor for professional developers",
        )
        result = normalize(raw, source_ids=["src_001"])
        desc = result.user_personas[0].description
        assert "AI-first" in desc or "professional" in desc

    def test_fallback_description_non_trivial_without_positioning(self):
        raw = _raw("Windsurf", ["Enterprise teams"])
        result = normalize(raw, source_ids=["src_001"])
        desc = result.user_personas[0].description
        assert len(desc) > len("Enterprise teams")
        assert PLACEHOLDER not in desc

    def test_explicit_user_personas_not_overridden_by_fallback(self):
        raw = _raw("Cursor", ["Developers"])
        raw = raw.model_copy(update={"user_personas": [
            RawUserPersona(name="Pro Dev", description="Experienced developer"),
        ]})
        result = normalize(raw, source_ids=["src_001"])
        assert len(result.user_personas) == 1
        assert result.user_personas[0].description == "Experienced developer"
