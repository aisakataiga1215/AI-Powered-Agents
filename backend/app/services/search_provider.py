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
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]: ...


class TavilySearchProvider:
    def __init__(self, api_key: str) -> None:
        self._client = TavilyClient(api_key=api_key)

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        response = self._client.search(query=query, max_results=max_results)
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

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        return []


def create_search_provider(api_key: str, enabled: bool) -> SearchProvider:
    """Return TavilySearchProvider when enabled+key present, else NullSearchProvider."""
    if enabled and api_key:
        return TavilySearchProvider(api_key)
    return NullSearchProvider()
