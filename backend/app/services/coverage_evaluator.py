"""Coverage evaluator.

Scores how well the collected sources cover a competitor's key pages.
Used by CollectorAgent to decide whether to fall back to demo fixtures.
"""

from dataclasses import dataclass, field

from app.schemas.source import SourceEvidence, SourceType

_OFFICIAL_TYPES = {
    SourceType.official_website,
    SourceType.pricing_page,
    SourceType.docs,
    SourceType.features_page,
    SourceType.security,
    SourceType.privacy,
}

WEAK_THRESHOLD = 40


@dataclass
class CoverageSummary:
    homepage: bool = False
    pricing: bool = False
    features_or_docs: bool = False
    security_or_privacy: bool = False
    score: int = field(init=False)

    def __post_init__(self) -> None:
        self.score = (
            (30 if self.homepage else 0)
            + (30 if self.pricing else 0)
            + (30 if self.features_or_docs else 0)
            + (10 if self.security_or_privacy else 0)
        )


def evaluate(sources: list[SourceEvidence]) -> CoverageSummary:
    """Evaluate coverage for one competitor's source list."""
    homepage = any(
        s.source_type is SourceType.official_website for s in sources
    )
    pricing = any(s.source_type is SourceType.pricing_page for s in sources)
    features_or_docs = any(
        s.source_type in (SourceType.features_page, SourceType.docs)
        for s in sources
    )
    security_or_privacy = any(
        s.source_type in (SourceType.security, SourceType.privacy)
        for s in sources
    )
    return CoverageSummary(
        homepage=homepage,
        pricing=pricing,
        features_or_docs=features_or_docs,
        security_or_privacy=security_or_privacy,
    )


def evaluate_per_competitor(
    sources: list[SourceEvidence],
) -> dict[str, CoverageSummary]:
    """Group sources by competitor_name and evaluate each independently."""
    by_competitor: dict[str, list[SourceEvidence]] = {}
    for source in sources:
        by_competitor.setdefault(source.competitor_name, []).append(source)
    return {
        name: evaluate(srcs) for name, srcs in by_competitor.items()
    }
