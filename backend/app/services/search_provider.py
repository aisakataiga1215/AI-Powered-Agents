"""Search provider abstraction.

TavilySearchProvider wraps the Tavily SDK. NullSearchProvider is a no-op
used when search is disabled or the API key is absent.
"""

from typing import Protocol, runtime_checkable

from pydantic import BaseModel
from tavily import TavilyClient


class SearchResult(BaseModel):
    url: str
    title: str
    snippet: str


@runtime_checkable
class SearchProvider(Protocol):
    def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "advanced",
        topic: str = "general",
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        exact_match: bool | None = None,
    ) -> list[SearchResult]: ...


class TavilySearchProvider:
    def __init__(self, api_key: str) -> None:
        self._client = TavilyClient(api_key=api_key)

    def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "advanced",
        topic: str = "general",
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        exact_match: bool | None = None,
    ) -> list[SearchResult]:
        kwargs: dict = {
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
            "topic": topic,
        }
        if include_domains:
            kwargs["include_domains"] = include_domains
        if exclude_domains:
            kwargs["exclude_domains"] = exclude_domains
        if exact_match is not None:
            kwargs["exact_match"] = exact_match

        response = self._client.search(**kwargs)
        return [
            SearchResult(
                url=r["url"],
                title=r.get("title", ""),
                snippet=r.get("content", ""),
            )
            for r in response.get("results", [])
            if r.get("url")
        ]


class NullSearchProvider:
    """No-op. Used when TAVILY_API_KEY is absent or ENABLE_LIVE_SEARCH=false."""

    def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "advanced",
        topic: str = "general",
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        exact_match: bool | None = None,
    ) -> list[SearchResult]:
        return []


def create_search_provider(api_key: str, enabled: bool) -> SearchProvider:
    """Return TavilySearchProvider when enabled+key present, else NullSearchProvider."""
    if enabled and api_key:
        return TavilySearchProvider(api_key)
    return NullSearchProvider()


def create_provider_from_settings() -> SearchProvider:
    """Factory for M15A interactive search. Reuses M14 activation flags."""
    from app.core.config import settings

    if settings.enable_live_search and settings.tavily_api_key:
        return TavilySearchProvider(settings.tavily_api_key)
    return NullSearchProvider()

