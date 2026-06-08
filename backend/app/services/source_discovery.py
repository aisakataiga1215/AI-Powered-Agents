"""Source discovery service.

Industry-specific candidate path probing from user-provided official URLs.
Constructs known path variants (e.g. /pricing, /seller-fees) and probes them
against the competitor's root domain. This is NOT full web discovery,
sitemap crawling, link following, or search-engine discovery.
"""

from urllib.parse import urlparse, urlunparse

_INDUSTRY_PATHS: dict[str, tuple[str, ...]] = {
    "ai_saas": (
        "/pricing",
        "/price",
        "/plans",
        "/features",
        "/docs",
        "/documentation",
        "/security",
        "/enterprise",
        "/api",
        "/integrations",
    ),
    "ecommerce": (
        # ordered by analysis value — transactional/seller pages first
        "/seller",
        "/sell",
        "/seller-fees",
        "/fees",
        "/shipping",
        "/returns",
        "/buyer-protection",
        "/subscriptions",
        "/prime",
        "/store",
        "/stores",
        "/advertising",
        "/help",
        "/customer-service",
    ),
    "local_services": (
        # ordered by analysis value — partner/driver pages first
        "/merchant",
        "/partner",
        "/business",
        "/driver",
        "/dasher",
        "/delivery",
        "/membership",
        "/pass",
        "/fees",
        "/help",
        "/pricing",
        "/consumer",
    ),
    "general": (
        "/about",
        "/pricing",
        "/features",
        "/help",
        "/docs",
        "/contact",
    ),
    "social": (
        "/advertising",
        "/ads",
        "/business",
        "/creator",
        "/monetize",
        "/premium",
        "/professional",
        "/subscriptions",
        "/for-business",
        "/help",
    ),
}

_INDUSTRY_MAX_PAGES: dict[str, int] = {
    "ai_saas": 5,
    "general": 5,
    "ecommerce": 8,
    "local_services": 8,
    "social": 6,
}

_DEFAULT_PATHS = _INDUSTRY_PATHS["general"]
_DEFAULT_MAX_PAGES = 5

# Backward-compat alias — existing tests import CANDIDATE_PATHS directly.
CANDIDATE_PATHS = list(_INDUSTRY_PATHS["ai_saas"])


def discover_pages(
    base_url: str,
    max_pages: int | None = None,
    industry_type: str = "general",
) -> list[str]:
    """Return up to max_pages candidate URLs on the same root domain.

    The homepage (normalized root) is always the first result. Remaining
    slots are filled from the industry-specific path list in order.

    Args:
        base_url: Competitor's official website URL.
        max_pages: Hard cap on returned URLs. None = use industry default.
        industry_type: One of "ai_saas", "ecommerce", "local_services", "general".
    """
    parsed = urlparse(base_url)
    netloc = parsed.netloc
    if not netloc:
        parsed = urlparse("https://" + base_url)
        netloc = parsed.netloc
    if not netloc:
        return []
    scheme = parsed.scheme or "https"
    root = urlunparse((scheme, netloc, "", "", "", ""))

    paths = _INDUSTRY_PATHS.get(industry_type, _DEFAULT_PATHS)
    effective_max = (
        max_pages
        if max_pages is not None
        else _INDUSTRY_MAX_PAGES.get(industry_type, _DEFAULT_MAX_PAGES)
    )

    candidates = [root] + [root + path for path in paths]
    seen: set[str] = set()
    result: list[str] = []
    for url in candidates:
        if url not in seen:
            seen.add(url)
            result.append(url)
        if len(result) >= effective_max:
            break
    return result


def get_industry_max_pages(industry_type: str) -> int:
    """Return the crawl-page cap for the given industry type."""
    return _INDUSTRY_MAX_PAGES.get(industry_type, _DEFAULT_MAX_PAGES)
