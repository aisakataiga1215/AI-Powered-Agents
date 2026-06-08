"""Tests: normalization_service routes evidence to type-appropriate sources.

When a list of SourceEvidence objects is passed to normalize(), pricing
claims should prefer pricing_page sources, feature claims should prefer
official_website/docs, and feedback claims should prefer review sources.
"""

from app.schemas.raw_extraction import RawCompetitorExtraction, RawFeature, RawPricingPlan
from app.schemas.source import Reliability, SourceEvidence, SourceType
from app.services.normalization_service import normalize


def _src(source_id: str, source_type: SourceType) -> SourceEvidence:
    return SourceEvidence(
        source_id=source_id,
        competitor_name="Cursor",
        source_type=source_type,
        url="https://cursor.com",
        title="test",
        reliability=Reliability.high,
    )


def _make_sources() -> list[SourceEvidence]:
    return [
        _src("src_home", SourceType.official_website),
        _src("src_pricing", SourceType.pricing_page),
        _src("src_docs", SourceType.docs),
        _src("src_review", SourceType.review),
    ]


def test_pricing_claim_prefers_pricing_page_source():
    """pricing_model.summary evidence should only include pricing_page source_id."""
    sources = _make_sources()
    all_ids = [s.source_id for s in sources]

    raw = RawCompetitorExtraction(
        name="Cursor",
        pricing_summary="Freemium with Pro at $20/month",
    )
    ck = normalize(raw, all_ids, sources=sources)

    assert ck.pricing_model.summary is not None
    evidence = ck.pricing_model.summary.evidence
    assert "src_pricing" in evidence
    # Must not include review source for a pricing claim
    assert "src_review" not in evidence


def test_pricing_plan_prefers_pricing_page_source():
    """pricing_model.plans[].evidence should prefer pricing_page source."""
    sources = _make_sources()
    all_ids = [s.source_id for s in sources]

    raw = RawCompetitorExtraction(
        name="Cursor",
        pricing_plans=[RawPricingPlan(name="Pro", price="$20")],
    )
    ck = normalize(raw, all_ids, sources=sources)

    assert len(ck.pricing_model.plans) == 1
    plan_evidence = ck.pricing_model.plans[0].evidence
    assert "src_pricing" in plan_evidence
    assert "src_review" not in plan_evidence


def test_feature_claim_prefers_official_website_and_docs():
    """feature_tree items should prefer official_website/docs sources."""
    sources = _make_sources()
    all_ids = [s.source_id for s in sources]

    raw = RawCompetitorExtraction(
        name="Cursor",
        features=[RawFeature(name="Tab completion", category="AI Coding")],
    )
    ck = normalize(raw, all_ids, sources=sources)

    assert len(ck.feature_tree) == 1
    feature_evidence = ck.feature_tree[0].features[0].evidence
    assert "src_home" in feature_evidence or "src_docs" in feature_evidence
    assert "src_pricing" not in feature_evidence


def test_feedback_claim_prefers_review_source():
    """positive_points/negative_points claims should prefer review source."""
    sources = _make_sources()
    all_ids = [s.source_id for s in sources]

    raw = RawCompetitorExtraction(
        name="Cursor",
        positive_points=["Fast AI completions"],
        negative_points=["Privacy concerns"],
    )
    ck = normalize(raw, all_ids, sources=sources)

    assert ck.user_feedback_summary is not None
    pos_evidence = ck.user_feedback_summary.positive_points[0].evidence
    neg_evidence = ck.user_feedback_summary.negative_points[0].evidence
    assert "src_review" in pos_evidence
    assert "src_review" in neg_evidence
    # Pricing source should not appear in feedback claims
    assert "src_pricing" not in pos_evidence
    assert "src_pricing" not in neg_evidence


def test_fallback_to_all_sources_when_no_typed_match():
    """If no source matches the preferred type, fall back to all source_ids."""
    # Only official_website -- no pricing_page -- no review
    sources_no_pricing = [
        _src("src_home", SourceType.official_website),
        _src("src_docs", SourceType.docs),
    ]
    all_ids = [s.source_id for s in sources_no_pricing]

    raw = RawCompetitorExtraction(
        name="Cursor",
        pricing_summary="Free plan available",
        positive_points=["Easy to use"],
    )
    ck = normalize(raw, all_ids, sources=sources_no_pricing)

    # Falls back to all source_ids when no pricing/review source exists
    if ck.pricing_model.summary:
        assert set(ck.pricing_model.summary.evidence).issubset(set(all_ids))
    if ck.user_feedback_summary and ck.user_feedback_summary.positive_points:
        assert set(ck.user_feedback_summary.positive_points[0].evidence).issubset(
            set(all_ids)
        )
