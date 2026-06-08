"""SearchService: web search → candidate URL list for CollectorAgent.

Fires industry-keyed queries against a SearchProvider, filters unsupported
URLs, deduplicates, and returns up to _SEARCH_MAX_URLS candidates.
Tavily title/snippet are used for discovery only — never stored as evidence.
"""

from urllib.parse import urlparse

from app.core.logging import get_logger
from app.services.search_provider import SearchProvider

logger = get_logger(__name__)

_SEARCH_MAX_URLS: int = 5

_QUERY_TEMPLATES: dict[str, list[str]] = {
    "ai_saas": [
        "{name} official pricing plans",
        "{name} official documentation",
        "{name} features overview",
        "{name} official help",
    ],
    "ecommerce": [
        "{name} seller fees official",
        "{name} store subscription fees",
        "{name} return policy",
        "{name} buyer protection policy",
    ],
    "local_services": [
        "{name} driver partner program",
        "{name} delivery fees",
        "{name} official help",
    ],
    "social": [
        "{name} advertising business",
        "{name} creator monetization",
        "{name} official help",
    ],
    "general": [
        "{name} official pricing",
        "{name} product features",
        "{name} official help",
    ],
}

_UNSUPPORTED_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf", ".zip", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".mp4", ".avi", ".mov", ".mp3",
})

_BLOCKED_DOMAINS: frozenset[str] = frozenset({
    "youtube.com", "youtu.be", "twitter.com", "x.com", "instagram.com",
    "facebook.com", "fb.com", "tiktok.com",
    # reddit.com blocked in M14 — community/review source support is tracked for a future milestone
    "reddit.com",
    "linkedin.com",  # auth wall makes crawling unreliable
    "bit.ly", "t.co", "goo.gl", "tinyurl.com",
})


def _is_crawlable(url: str) -> bool:
    """Return False for URLs with unsupported file extensions or blocked domains."""
    parsed = urlparse(url.lower())
    if any(parsed.path.endswith(ext) for ext in _UNSUPPORTED_EXTENSIONS):
        return False
    netloc = parsed.netloc.removeprefix("www.")
    if any(netloc == d or netloc.endswith("." + d) for d in _BLOCKED_DOMAINS):
        return False
    return True


def _normalize_url(url: str) -> str:
    """Simple normalization for internal deduplication of search results."""
    return url.rstrip("/").lower()


class SearchService:
    def __init__(self, provider: SearchProvider) -> None:
        self._provider = provider

    def discover_urls(
        self,
        competitor_name: str,
        competitor_url: str,
        industry_type: str = "general",
        max_per_query: int = 3,
    ) -> list[str]:
        """Fire industry-keyed queries, filter, deduplicate, return up to _SEARCH_MAX_URLS URLs."""
        templates = _QUERY_TEMPLATES.get(industry_type, _QUERY_TEMPLATES["general"])
        seen: set[str] = set()
        result: list[str] = []

        for template in templates:
            query = template.format(name=competitor_name)
            try:
                hits = self._provider.search(query, max_results=max_per_query)
            except Exception as exc:
                logger.warning("SearchService: query '%s' failed: %s", query, exc)
                continue

            for hit in hits:
                if not _is_crawlable(hit.url):
                    continue
                norm = _normalize_url(hit.url)
                if norm in seen:
                    continue
                seen.add(norm)
                result.append(hit.url)
                if len(result) >= _SEARCH_MAX_URLS:
                    return result

        return result
