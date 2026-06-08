"""Tests for search_provider, search_service, and CollectorAgent search integration."""

from unittest.mock import MagicMock, patch

import pytest

from app.schemas.source import SourceType
from app.services.crawler_service import CrawledPage


def _make_db():
    return MagicMock()


def _make_page(url: str, title: str = "Page", content: str = "") -> CrawledPage:
    return CrawledPage(
        url=url,
        title=title,
        snippet=content[:300],
        content=content,
        status_code=200,
        robots_status="allowed",
    )


# ---------------------------------------------------------------------------
# TestSearchProvider
# ---------------------------------------------------------------------------


class TestSearchProvider:
    def test_null_provider_returns_empty(self):
        from app.services.search_provider import NullSearchProvider

        provider = NullSearchProvider()
        assert provider.search("cursor pricing") == []

    def test_create_provider_no_key_returns_null(self):
        from app.services.search_provider import NullSearchProvider, create_search_provider

        provider = create_search_provider(api_key="", enabled=True)
        assert isinstance(provider, NullSearchProvider)

    def test_create_provider_disabled_returns_null(self):
        from app.services.search_provider import NullSearchProvider, create_search_provider

        provider = create_search_provider(api_key="sk-test", enabled=False)
        assert isinstance(provider, NullSearchProvider)

    def test_create_provider_with_key_returns_tavily(self):
        from app.services.search_provider import TavilySearchProvider, create_search_provider

        with patch("app.services.search_provider.TavilyClient"):
            provider = create_search_provider(api_key="sk-test", enabled=True)
        assert isinstance(provider, TavilySearchProvider)

    def test_tavily_provider_maps_sdk_response_to_search_result(self):
        from app.services.search_provider import SearchResult, TavilySearchProvider

        with patch("app.services.search_provider.TavilyClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.search.return_value = {
                "results": [
                    {
                        "url": "https://cursor.com/pricing",
                        "title": "Cursor Pricing",
                        "content": "$20/month",
                    }
                ]
            }
            provider = TavilySearchProvider(api_key="sk-test")
            results = provider.search("cursor pricing")

        assert len(results) == 1
        assert isinstance(results[0], SearchResult)
        assert results[0].url == "https://cursor.com/pricing"
        assert results[0].title == "Cursor Pricing"
        assert results[0].snippet == "$20/month"


# ---------------------------------------------------------------------------
# TestSearchService
# ---------------------------------------------------------------------------


class TestSearchService:
    def _make_service(self, urls: list[str]):
        """Return a SearchService backed by a mock provider yielding the given URLs."""
        from app.services.search_provider import SearchResult
        from app.services.search_service import SearchService

        mock_provider = MagicMock()
        mock_provider.search.return_value = [
            SearchResult(url=u, title="", snippet="") for u in urls
        ]
        return SearchService(mock_provider)

    def test_deduplicates_urls(self):
        svc = self._make_service(
            ["https://cursor.com/pricing", "https://cursor.com/pricing/"]
        )
        urls = svc.discover_urls("Cursor", "https://cursor.com", "general")
        normalized = [u.rstrip("/").lower() for u in urls]
        assert len(set(normalized)) == len(normalized)

    def test_caps_at_search_max_urls(self):
        from app.services.search_service import _SEARCH_MAX_URLS

        svc = self._make_service(
            [f"https://example.com/page{i}" for i in range(20)]
        )
        urls = svc.discover_urls("Example", "https://example.com", "general")
        assert len(urls) <= _SEARCH_MAX_URLS

    def test_filters_unsupported_extensions(self):
        svc = self._make_service(
            ["https://example.com/brochure.pdf", "https://example.com/pricing"]
        )
        urls = svc.discover_urls("Example", "https://example.com", "general")
        assert not any(u.endswith(".pdf") for u in urls)
        assert "https://example.com/pricing" in urls

    def test_filters_social_domains(self):
        svc = self._make_service(
            ["https://youtube.com/watch?v=xxx", "https://example.com/docs"]
        )
        urls = svc.discover_urls("Example", "https://example.com", "general")
        assert not any("youtube.com" in u for u in urls)
        assert "https://example.com/docs" in urls

    def test_handles_per_query_error_gracefully(self):
        from app.services.search_service import SearchService

        mock_provider = MagicMock()
        mock_provider.search.side_effect = Exception("Tavily rate limit exceeded")
        svc = SearchService(mock_provider)
        urls = svc.discover_urls("Example", "https://example.com", "general")
        assert urls == []


# ---------------------------------------------------------------------------
# TestCollectorAgentWithSearch
# ---------------------------------------------------------------------------


class TestCollectorAgentWithSearch:
    def test_search_urls_tagged_data_source_search(self):
        from app.agents import collector_agent

        home_page = _make_page("https://cursor.com", "Home", "AI IDE")
        search_page = _make_page(
            "https://cursor.com/blog/pricing-update",
            "Blog",
            "pricing update post",
        )

        mock_search_svc = MagicMock()
        mock_search_svc.discover_urls.return_value = [
            "https://cursor.com/blog/pricing-update"
        ]

        with (
            patch.object(
                collector_agent.source_discovery,
                "discover_pages",
                return_value=["https://cursor.com"],
            ),
            patch.object(
                collector_agent.crawler_service,
                "crawl_page",
                side_effect=[home_page, search_page],
            ),
            patch.object(collector_agent.crawler_service, "fixture_exists", return_value=False),
            patch.object(collector_agent.source_service, "save_sources"),
            patch.object(collector_agent.trace_service, "save_agent_run"),
            patch.object(collector_agent.trace_service, "update_agent_run"),
        ):
            result = collector_agent.run(
                db=_make_db(),
                project_id="proj_1",
                competitors=[{"name": "Cursor", "url": "https://cursor.com"}],
                goals=[],
                data_mode="live_with_fallback",
                _search_service=mock_search_svc,
            )

        search_sources = [s for s in result if s.data_source == "search"]
        assert len(search_sources) == 1
        assert "blog" in search_sources[0].url

        live_sources = [s for s in result if s.data_source == "live"]
        assert len(live_sources) == 1

    def test_search_error_does_not_fail_workflow(self):
        from app.agents import collector_agent

        home_page = _make_page("https://cursor.com", "Home", "AI IDE")

        class _FailingSearchService:
            def discover_urls(self, *args, **kwargs):
                raise RuntimeError("Network error in search")

        with (
            patch.object(
                collector_agent.source_discovery,
                "discover_pages",
                return_value=["https://cursor.com"],
            ),
            patch.object(
                collector_agent.crawler_service, "crawl_page", return_value=home_page
            ),
            patch.object(collector_agent.crawler_service, "fixture_exists", return_value=False),
            patch.object(collector_agent.source_service, "save_sources"),
            patch.object(collector_agent.trace_service, "save_agent_run"),
            patch.object(collector_agent.trace_service, "update_agent_run"),
        ):
            result = collector_agent.run(
                db=_make_db(),
                project_id="proj_1",
                competitors=[{"name": "Cursor", "url": "https://cursor.com"}],
                goals=[],
                data_mode="live_with_fallback",
                _search_service=_FailingSearchService(),
            )

        # Known-path sources still collected despite search failure
        assert len(result) >= 1
        assert all(s.data_source in ("live", "demo") for s in result)
