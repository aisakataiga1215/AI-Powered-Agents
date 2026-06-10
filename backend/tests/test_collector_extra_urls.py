"""Tests for CollectorAgent extra_urls (M15A) — user-selected candidate source URLs."""

from unittest.mock import MagicMock, call, patch

import pytest

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


def _run_with_extra_urls(extra_urls: list[str], crawl_pages: dict[str, CrawledPage | None]):
    """Helper: run CollectorAgent with mocked crawler, returning list of SourceEvidence."""
    from app.agents import collector_agent

    def fake_crawl(url: str):
        return crawl_pages.get(url)

    class _NullSearch:
        def discover_urls(self, *a, **kw):
            return []

    with (
        patch.object(collector_agent.source_discovery, "discover_pages", return_value=[]),
        patch.object(collector_agent.crawler_service, "crawl_page", side_effect=fake_crawl),
        patch.object(collector_agent.crawler_service, "fixture_exists", return_value=False),
        patch.object(collector_agent.source_service, "save_sources"),
        patch.object(collector_agent.trace_service, "save_agent_run"),
        patch.object(collector_agent.trace_service, "update_agent_run"),
    ):
        return collector_agent.run(
            db=_make_db(),
            project_id="proj_test",
            competitors=[{"name": "Cursor", "url": "https://cursor.com", "extra_urls": extra_urls}],
            goals=[],
            data_mode="live_with_fallback",
            _search_service=_NullSearch(),
        )


class TestCollectorExtraUrls:
    def test_extra_urls_are_crawled(self):
        extra = "https://cursor.com/pricing"
        pages = {extra: _make_page(extra, "Cursor Pricing", "price per month")}
        sources = _run_with_extra_urls([extra], pages)
        assert any(s.url == extra for s in sources)

    def test_extra_url_tagged_data_source_search(self):
        extra = "https://cursor.com/pricing"
        pages = {extra: _make_page(extra, "Pricing", "price per month")}
        sources = _run_with_extra_urls([extra], pages)
        matching = [s for s in sources if s.url == extra]
        assert matching
        assert matching[0].data_source == "search"

    def test_unselected_url_not_crawled(self):
        """URL absent from extra_urls and from search results must not appear in sources."""
        unselected = "https://cursor.com/secret-page"
        # M14 search returns empty (mocked via _NullSearch in helper)
        # extra_urls does not include unselected URL
        sources = _run_with_extra_urls([], {unselected: _make_page(unselected)})
        assert not any(s.url == unselected for s in sources)

    def test_tavily_snippet_not_stored_as_content(self):
        """SourceEvidence.content comes from CrawlerService, not CandidateSource.snippet."""
        from app.schemas.search import CandidateSource
        from app.schemas.source import SourceType

        candidate = CandidateSource(
            competitor_name="Cursor",
            url="https://cursor.com/pricing",
            title="Cursor Pricing",
            snippet="TAVILY_SNIPPET_DO_NOT_STORE",
        )
        # Simulate what happens after user selects this URL:
        # only the URL is passed as extra_url, snippet is discarded
        crawled_content = "Real crawled content from the page"
        pages = {candidate.url: _make_page(candidate.url, "Pricing", crawled_content)}
        sources = _run_with_extra_urls([candidate.url], pages)

        matching = [s for s in sources if s.url == candidate.url]
        assert matching
        assert "TAVILY_SNIPPET_DO_NOT_STORE" not in matching[0].content
        assert crawled_content in matching[0].content

    def test_demo_mode_ignores_extra_urls(self):
        """demo mode skips _collect_live — extra_urls never reached."""
        from app.agents import collector_agent

        with (
            patch.object(collector_agent.crawler_service, "load_demo_fixtures", return_value=[]),
            patch.object(collector_agent.source_service, "save_sources"),
            patch.object(collector_agent.trace_service, "save_agent_run"),
            patch.object(collector_agent.trace_service, "update_agent_run"),
            patch.object(collector_agent.crawler_service, "crawl_page") as mock_crawl,
        ):
            collector_agent.run(
                db=_make_db(),
                project_id="proj_test",
                competitors=[{
                    "name": "Cursor",
                    "url": "https://cursor.com",
                    "extra_urls": ["https://cursor.com/pricing"],
                }],
                goals=[],
                data_mode="demo",
            )
            mock_crawl.assert_not_called()

    def test_extra_urls_are_normalized_and_filtered(self):
        """Blocked domain in extra_urls is excluded; crawl is not called for it."""
        from app.agents import collector_agent

        blocked = "https://youtube.com/watch?v=cursor-demo"
        valid = "https://cursor.com/pricing"

        with (
            patch.object(collector_agent.source_discovery, "discover_pages", return_value=[]),
            patch.object(collector_agent.crawler_service, "crawl_page",
                         side_effect=lambda url: _make_page(url)) as mock_crawl,
            patch.object(collector_agent.crawler_service, "fixture_exists", return_value=False),
            patch.object(collector_agent.source_service, "save_sources"),
            patch.object(collector_agent.trace_service, "save_agent_run"),
            patch.object(collector_agent.trace_service, "update_agent_run"),
        ):
            class _NullSearch:
                def discover_urls(self, *a, **kw):
                    return []

            collector_agent.run(
                db=_make_db(),
                project_id="proj_test",
                competitors=[{
                    "name": "Cursor",
                    "url": "https://cursor.com",
                    "extra_urls": [blocked, valid],
                }],
                goals=[],
                data_mode="live_with_fallback",
                _search_service=_NullSearch(),
            )
            crawled_urls = [c.args[0] for c in mock_crawl.call_args_list]
            assert blocked not in crawled_urls
            assert valid in crawled_urls

    def test_rejected_extra_url_in_trace_output(self):
        """Filtered extra_url appears in rejected_extra_urls in collection_stats trace."""
        from app.agents import collector_agent

        blocked = "https://youtube.com/watch?v=abc"
        captured_output = {}

        def capture_update(db, run_id, **kwargs):
            if "output" in kwargs:
                captured_output.update(kwargs["output"])

        class _NullSearch:
            def discover_urls(self, *a, **kw):
                return []

        with (
            patch.object(collector_agent.source_discovery, "discover_pages", return_value=[]),
            patch.object(collector_agent.crawler_service, "crawl_page", return_value=None),
            patch.object(collector_agent.crawler_service, "fixture_exists", return_value=False),
            patch.object(collector_agent.source_service, "save_sources"),
            patch.object(collector_agent.trace_service, "save_agent_run"),
            patch.object(collector_agent.trace_service, "update_agent_run",
                         side_effect=capture_update),
        ):
            collector_agent.run(
                db=_make_db(),
                project_id="proj_test",
                competitors=[{
                    "name": "Cursor",
                    "url": "https://cursor.com",
                    "extra_urls": [blocked],
                }],
                goals=[],
                data_mode="live_with_fallback",
                _search_service=_NullSearch(),
            )

        stats = captured_output.get("collection_stats_by_competitor", {}).get("Cursor", {})
        rejected = stats.get("rejected_extra_urls", [])
        assert any(r["url"] == blocked for r in rejected)
        assert all("reason" in r for r in rejected)

    def test_extra_urls_reject_private_hosts(self):
        """Private network targets are rejected before crawl."""
        from app.agents import collector_agent

        blocked = "http://127.0.0.1:8000/admin"
        captured_output = {}

        def capture_update(db, run_id, **kwargs):
            if "output" in kwargs:
                captured_output.update(kwargs["output"])

        class _NullSearch:
            def discover_urls(self, *a, **kw):
                return []

        with (
            patch.object(collector_agent.source_discovery, "discover_pages", return_value=[]),
            patch.object(collector_agent.crawler_service, "crawl_page", return_value=None) as mock_crawl,
            patch.object(collector_agent.crawler_service, "fixture_exists", return_value=False),
            patch.object(collector_agent.source_service, "save_sources"),
            patch.object(collector_agent.trace_service, "save_agent_run"),
            patch.object(collector_agent.trace_service, "update_agent_run", side_effect=capture_update),
        ):
            collector_agent.run(
                db=_make_db(),
                project_id="proj_test",
                competitors=[{
                    "name": "Cursor",
                    "url": "https://cursor.com",
                    "extra_urls": [blocked],
                }],
                goals=[],
                data_mode="live_with_fallback",
                _search_service=_NullSearch(),
            )

        crawled_urls = [c.args[0] for c in mock_crawl.call_args_list]
        assert blocked not in crawled_urls
        stats = captured_output.get("collection_stats_by_competitor", {}).get("Cursor", {})
        assert any(r["url"] == blocked for r in stats.get("rejected_extra_urls", []))
