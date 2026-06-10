"""Source classifier.

Maps a crawled page's URL, title, and content to a SourceType.

Priority order:
1. URL-path match → content validation confirms the candidate type.
   If content is non-empty and lacks matching keywords → SourceType.unknown.
   If content is empty → trust the URL path (backward-compat, test-friendly).
2. Path is root → official_website (only if domain is not a third-party host).
3. No path match → content-keyword fallback (pricing signals, docs signals).
4. Default → unknown.
"""

from urllib.parse import urlparse

from app.schemas.source import SourceType

# M16.2: third-party hosting platforms — root path on these is NOT an official_website
_THIRD_PARTY_HOSTING_DOMAINS: frozenset[str] = frozenset({
    "readthedocs.io", "readthedocs.org", "gitbook.io", "notion.site",
    "github.io",  # github pages (e.g. openearth/windsurf)
    "vercel.app", "netlify.app", "pages.dev",
    "confluence.atlassian.net",
})

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
    parsed = urlparse(url)
    path = parsed.path.lower().rstrip("/")
    domain = parsed.netloc.removeprefix("www.").lower()

    candidate: SourceType | None = None
    if "/privacy" in path:
        candidate = SourceType.privacy
    elif "/security" in path:
        candidate = SourceType.security
    elif any(seg in path for seg in ("/terms", "/legal", "/policy")):
        candidate = SourceType.unknown
    elif any(seg in path for seg in ("/pricing", "/price", "/plans", "/usage")):
        candidate = SourceType.pricing_page
    elif "/features" in path or "/compare" in path:
        candidate = SourceType.features_page
    elif path == "/blog" or path.endswith("/blog"):
        candidate = SourceType.blog
    elif domain.startswith("docs.") or any(seg in path for seg in ("/docs", "/documentation", "/api")):
        candidate = SourceType.docs
    elif path in ("", "/"):
        # M16.2: third-party hosting platforms are not official_website even at root
        is_third_party = any(
            domain == d or domain.endswith("." + d)
            for d in _THIRD_PARTY_HOSTING_DOMAINS
        )
        if not is_third_party:
            return SourceType.official_website  # homepage: always valid

    if candidate is not None:
        return (
            candidate
            if _validate_by_content(candidate, title, content)
            else SourceType.unknown
        )

    if any(seg in path for seg in ("/download", "/terms", "/legal", "/policy", "/blog")):
        return SourceType.unknown

    combined = f"{title} {content}".lower()
    pricing_signals = sum(
        1
        for kw in _CONTENT_VALIDATORS[SourceType.pricing_page]
        if kw in combined
    )
    if "pricing" in combined and ("per month" in combined or "per user" in combined or "subscription" in combined):
        return SourceType.pricing_page
    if "our plans" in combined and pricing_signals >= 3:
        return SourceType.pricing_page
    if any(kw in combined for kw in _CONTENT_VALIDATORS[SourceType.features_page]):
        return SourceType.features_page
    if any(kw in combined for kw in _CONTENT_VALIDATORS[SourceType.docs]):
        return SourceType.docs

    return SourceType.unknown
