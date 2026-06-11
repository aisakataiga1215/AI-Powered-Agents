"""Normalization service.

Converts a :class:`~app.schemas.raw_extraction.RawCompetitorExtraction`
(the flat, LLM-friendly representation) into the strict
:class:`~app.schemas.knowledge.CompetitorKnowledge` expected by the
AnalystAgent's downstream callers.

Every ``str`` claim field becomes a :class:`~app.schemas.claim.Claim`
with ``evidence=source_ids`` and ``created_by="AnalystAgent"``.
Empty strings and empty lists are silently dropped rather than producing
empty-text Claim objects that QA would flag as invalid evidence.

Design decisions:
- ``is_hypothesis=False`` when we have at least one source_id (the analyst
  read those documents to produce the claim).
- ``is_hypothesis=True`` only when source_ids is empty at call time, which
  should not happen in production but is tolerated gracefully.
- Features are grouped by ``RawFeature.category``; categories are created
  on first encounter, preserving insertion order.
- Feature categories are normalized via ``CATEGORY_ALIASES`` so that LLM
  label variants like "AI Agent" / "AI Agents" / "Agentic Editing" all map
  to the same canonical row in the report table.
"""

import uuid
from collections import OrderedDict

from app.schemas.claim import Claim, ConfidenceLevel, Sentence
from app.schemas.knowledge import (
    CompetitorKnowledge,
    FeatureCategory,
    FeatureItem,
    PricingModel,
    PricingPlan,
    ProductProfile,
    SWOTAnalysis,
    UserFeedbackSummary,
    UserPersona,
)
from app.schemas.raw_extraction import (
    RawCompetitorExtraction,
    RawFeature,
    RawPricingPlan,
    RawUserPersona,
)

# ---------------------------------------------------------------------------
# Feature taxonomy normalization
# ---------------------------------------------------------------------------

CATEGORY_ALIASES: dict[str, str] = {
    # AI Agents cluster
    "ai agent": "AI Agents",
    "ai agents": "AI Agents",
    "agent": "AI Agents",
    "agentic editing": "AI Agents",
    "agent command center": "AI Agents",
    "trae solo": "AI Agents",
    "agent requests": "AI Agents",
    "agent management": "AI Agents",
    "agent execution": "AI Agents",
    # Cloud Agents — distinct canonical (not merged into AI Agents)
    "cloud agents": "Cloud Agents",
    "devin cloud": "Cloud Agents",
    # Code generation cluster
    "code gen": "Code Generation",
    "code generation": "Code Generation",
    # Code completion cluster
    "autocomplete": "Code Completion",
    "auto-complete": "Code Completion",
    "inline completion": "Code Completion",
    "code completion": "Code Completion",
}


def normalize_feature_category(category: str) -> str:
    """Return the canonical category name for a given raw LLM-emitted category.

    Lookup is case-insensitive. Unknown categories are returned stripped
    and unchanged so new categories are never silently dropped.
    """
    return CATEGORY_ALIASES.get(category.strip().lower(), category.strip())


# ---------------------------------------------------------------------------


_AVAILABILITY_MAP = {
    "yes": "available",
    "true": "available",
    "1": "available",
    "no": "unknown",
    "false": "unknown",
    "0": "unknown",
    "partial": "limited",
    "partially": "limited",
    "limited": "limited",
    "available": "available",
    "unknown": "unknown",
    "n/a": "unknown",
}


def _typed_source_ids(
    sources: list,  # list[SourceEvidence] - avoid circular import; duck-typed
    preferred_types: set[str],
    fallback: list[str],
) -> list[str]:
    """Return source_ids whose source_type is in preferred_types.

    Falls back to ``fallback`` when no matching source exists, so claims
    are never left with an empty evidence list when sources are available.
    """
    ids = [
        s.source_id
        for s in sources
        if getattr(s, "source_type", None) is not None
        and s.source_type.value in preferred_types
    ]
    return ids if ids else fallback


def _availability(value: str) -> str:
    """Normalise free-form availability strings to the three allowed values."""
    return _AVAILABILITY_MAP.get(value.strip().lower(), "available")


def _make_claim(
    text: str,
    source_ids: list[str],
    confidence: ConfidenceLevel = ConfidenceLevel.medium,
) -> Claim | None:
    """Wrap a plain string in a Claim. Returns None for empty/whitespace text."""
    stripped = (text or "").strip()
    if not stripped:
        return None
    sentence = Sentence(text=stripped, sources=list(source_ids))
    return Claim(
        claim_id=f"claim_{uuid.uuid4().hex[:8]}",
        text=stripped,
        confidence=confidence,
        evidence=list(source_ids),
        sentences=[sentence],
        is_hypothesis=not bool(source_ids),
        created_by="AnalystAgent",
    )


def _make_claims(texts: list[str], source_ids: list[str]) -> list[Claim]:
    """Convert a list of strings to a list of Claims, dropping empty entries."""
    claims = [_make_claim(t, source_ids) for t in (texts or [])]
    return [c for c in claims if c is not None]


def _normalize_features(
    raw_features: list[RawFeature],
    source_ids: list[str],
) -> list[FeatureCategory]:
    """Group raw features by category preserving insertion order."""
    cats: OrderedDict[str, list[FeatureItem]] = OrderedDict()
    for rf in raw_features:
        category = normalize_feature_category(rf.category or "General")
        item = FeatureItem(
            name=rf.name.strip(),
            description=(rf.description or "").strip(),
            availability=_availability(rf.availability),
            evidence=list(source_ids),
        )
        cats.setdefault(category, []).append(item)
    return [
        FeatureCategory(category=cat, features=items)
        for cat, items in cats.items()
    ]


def _normalize_pricing_plans(
    raw_plans: list[RawPricingPlan],
    source_ids: list[str],
) -> list[PricingPlan]:
    return [
        PricingPlan(
            name=p.name.strip(),
            price=(p.price or "").strip(),
            billing_cycle=(p.billing_cycle or "monthly").strip(),
            features=list(p.features),
            evidence=list(source_ids),
        )
        for p in raw_plans
        if (p.name or "").strip()
    ]


def _normalize_user_personas(
    raw_personas: list[RawUserPersona],
    source_ids: list[str],
) -> list[UserPersona]:
    return [
        UserPersona(
            name=p.name.strip(),
            description=(p.description or "").strip(),
            needs=list(p.needs),
            pain_points=list(p.pain_points),
            evidence=list(source_ids),
        )
        for p in raw_personas
        if (p.name or "").strip()
    ]


def _derive_persona_description(user_text: str, product: str, pos_hint: str) -> str:
    """Build a useful one-sentence persona description from available context.

    Priority:
    1. user_text + product + positioning hint (when positioning present)
    2. Long descriptive user_text + product context
    3. Short generic user_text — lead with the product name
    """
    if pos_hint:
        return f"{user_text} using {product} — {pos_hint}"
    if len(user_text) > 15:
        return f"{user_text} — primary user segment for {product}"
    return f"{product} targets {user_text.lower()} as a primary user segment"


def normalize(
    raw: RawCompetitorExtraction,
    source_ids: list[str],
    competitor_id: str = "",
    sources: list | None = None,   # list[SourceEvidence]; optional typed routing
) -> CompetitorKnowledge:
    """Convert a :class:`RawCompetitorExtraction` to :class:`CompetitorKnowledge`.

    Args:
        raw: The flat extraction produced by the LLM.
        source_ids: Source IDs for the competitor; attached as evidence on
            every generated Claim.
        competitor_id: Optional pre-assigned ID; generated if empty.
        sources: Optional list of ``SourceEvidence`` objects. When provided,
            evidence for feature/pricing/feedback claims is routed to the
            most relevant ``source_type`` (e.g. pricing claims cite
            ``pricing_page`` sources). When omitted, all claims receive the
            full ``source_ids`` list.

    Returns:
        A fully validated :class:`CompetitorKnowledge` instance.
    """
    cid = competitor_id or f"comp_{uuid.uuid4().hex[:8]}"

    # Compute type-filtered source_id lists when SourceEvidence objects are provided.
    # Falls back to the full source_ids list when sources is not provided (tests,
    # backward-compat callers).
    pricing_source_ids: list[str] = source_ids
    feature_source_ids: list[str] = source_ids
    feedback_source_ids: list[str] = source_ids

    if sources:
        pricing_source_ids = _typed_source_ids(
            sources, {"pricing_page"}, source_ids
        )
        feature_source_ids = _typed_source_ids(
            sources, {"official_website", "docs"}, source_ids
        )
        feedback_source_ids = _typed_source_ids(
            sources, {"review"}, source_ids
        )

    # --- ProductProfile ---------------------------------------------------
    positioning_claim = _make_claim(raw.positioning, source_ids)
    target_user_claims = _make_claims(raw.target_users, source_ids)
    profile = ProductProfile(
        name=raw.name.strip(),
        website=(raw.website or "").strip(),
        company=(raw.company or "").strip(),
        positioning=positioning_claim,
        target_users=target_user_claims,
    )

    # --- FeatureTree ------------------------------------------------------
    feature_tree = _normalize_features(raw.features, feature_source_ids)

    # --- PricingModel -----------------------------------------------------
    plans = _normalize_pricing_plans(raw.pricing_plans, pricing_source_ids)
    pricing_summary_claim = _make_claim(raw.pricing_summary, pricing_source_ids)
    pricing = PricingModel(
        has_free_plan=raw.has_free_plan,
        pricing_url=(raw.pricing_url or "").strip(),
        plans=plans,
        summary=pricing_summary_claim,
    )

    # --- UserPersonas & feedback ------------------------------------------
    user_personas = _normalize_user_personas(raw.user_personas, source_ids)
    # Derive simple personas from product_profile.target_users when the LLM
    # did not produce any explicit user_personas.
    if not user_personas and raw.target_users:
        product = raw.name.strip()
        pos_hint = ""
        if raw.positioning:
            first_sentence = raw.positioning.strip().split(".")[0].strip()
            if len(first_sentence) > 10:
                pos_hint = first_sentence[:80]
        user_personas = [
            UserPersona(
                name=user_text.strip(),
                description=_derive_persona_description(user_text.strip(), product, pos_hint),
                evidence=list(source_ids),
            )
            for user_text in raw.target_users
            if user_text.strip()
        ]

    pos_claims = _make_claims(raw.positive_points, feedback_source_ids)
    neg_claims = _make_claims(raw.negative_points, feedback_source_ids)
    feedback_summary_text = (raw.user_feedback_summary or "").strip()
    user_feedback: UserFeedbackSummary | None = None
    if pos_claims or neg_claims or feedback_summary_text:
        user_feedback = UserFeedbackSummary(
            positive_points=pos_claims,
            negative_points=neg_claims,
            summary=feedback_summary_text,
        )

    # --- SWOT -------------------------------------------------------------
    swot = SWOTAnalysis(
        strengths=_make_claims(raw.strengths, source_ids),
        weaknesses=_make_claims(raw.weaknesses, source_ids),
        opportunities=_make_claims(raw.opportunities, source_ids),
        threats=_make_claims(raw.threats, source_ids),
    )

    return CompetitorKnowledge(
        competitor_id=cid,
        competitor_name=raw.name.strip(),
        product_profile=profile,
        feature_tree=feature_tree,
        pricing_model=pricing,
        user_personas=user_personas,
        user_feedback_summary=user_feedback,
        swot=swot,
        sources=list(source_ids),
    )
