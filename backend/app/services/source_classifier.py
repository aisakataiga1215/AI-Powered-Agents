"""Source classifier.

Maps a crawled page's URL, title, and content to a SourceType.

Priority order:
1. URL-path match → content validation confirms the candidate type.
   If content is non-empty and lacks matching keywords → SourceType.unknown.
   If content is empty → trust the URL path (backward-compat, test-friendly).
2. Path is root → official_website (always valid, no content check).
3. No path match → content-keyword fallback (pricing signals, docs signals).
4. Default → unknown.
"""

from urllib.parse import urlparse

from app.schemas.source import SourceType

_CONTENT_VALIDATORS: dict[SourceType, tuple[str, ...]] = {
    SourceType.pricing_page: (
        "price",
        "pricing",
        "per month",
        "per user",
        "$/mo",
        "plan",
        "subscription",
        "free tier",
        "enterprise",
    ),
    SourceType.features_page: (
        "feature",
        "product",
        "capability",
        "what you get",
        "how it works",
        "built for",
        "includes",
    ),
    SourceType.docs: (
        "documentation",
        "reference",
        "guide",
        "getting started",
        "api",
        "sdk",
        "quickstart",
    ),
}


def _validate_by_content(source_type: SourceType, title: str, content: str) -> bool:
    """Return True if title+content confirms the URL-path classification.

    Returns True when:
    - source_type has no content validator (official_website, security, privacy)
    - content is empty/whitespace (no crawled data — trust URL path)
    - combined title+content contains at least one matching keyword

    Returns False (→ caller downgrades to unknown) when content is non-empty
    but contains no keywords for the declared type.
    """
    keywords = _CONTENT_VALIDATORS.get(source_type)
    if keywords is None:
        return True  # official_website, security, privacy — always valid
    combined = (title + " " + content).strip()
    if not combined:
        return True  # no content to validate — trust URL path
    return any(kw in combined.lower() for kw in keywords)


def classify(url: str, title: str, content: str) -> SourceType:
    """Return the most specific SourceType that matches the page.

    URL path provides the initial candidate. When content is available,
    it must confirm the URL-path classification; otherwise the source is
    downgraded to unknown so the QA agent can flag it.
    """
    path = urlparse(url).path.lower().rstrip("/")

    candidate: SourceType | None = None
    if any(seg in path for seg in ("/pricing", "/price", "/plans")):
        candidate = SourceType.pricing_page
    elif "/features" in path:
        candidate = SourceType.features_page
    elif any(seg in path for seg in ("/docs", "/documentation", "/api")):
        candidate = SourceType.docs
    elif "/security" in path:
        candidate = SourceType.security
    elif "/privacy" in path:
        candidate = SourceType.privacy
    elif path in ("", "/"):
        return SourceType.official_website  # homepage: always valid

    if candidate is not None:
        return (
            candidate
            if _validate_by_content(candidate, title, content)
            else SourceType.unknown
        )

    # No path match — fall through to content-keyword detection
    combined = (title + " " + content).lower()
    pricing_signals = ("pricing", "per month", "per user", "subscription", "/mo", "/yr")
    if any(sig in combined for sig in pricing_signals):
        return SourceType.pricing_page
    docs_signals = ("documentation", "api reference", "getting started", "code example")
    if any(sig in combined for sig in docs_signals):
        return SourceType.docs

    return SourceType.unknown
