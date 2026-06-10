"""Tests for CollectorAgent live crawl path and fallback behavior."""

from unittest.mock import MagicMock, patch

import pytest

from app.schemas.source import Reliability, SourceEvidence, SourceType
from app.services.crawler_service import CrawledPage


def _make_db():
    """Return a mock database session."""
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


def _make_source(competitor_name: str, source_type: SourceType, data_source: str = "demo") -> SourceEvidence:
    return SourceEvidence(
        competitor_name=competitor_name,
        source_type=source_type,
        url=f"https://example.com/{source_type.value}",
        title=f"{competitor_name} {source_type.value}",
        data_source=data_source,  # type: ignore[arg-type]
    )


class TestCollectorAgentDemo:
    def test_demo_mode_does_not_call_crawl_page(self):
        from app.agents import collector_agent

        with (
            patch.object(collector_agent.crawler_service, "load_demo_fixtures") as mock_fixtures,
            patch.object(collector_agent.crawler_service, "crawl_page") as mock_crawl,
            patch.object(collector_agent.source_service, "save_sources"),
            patch.object(collector_agent.trace_service, "save_agent_run"),
            patch.object(collector_agent.trace_service, "update_agent_run"),
        ):
            mock_fixtures.return_value = [
                _make_source("Cursor", SourceType.official_website)
            ]
            result = collector_agent.run(
                db=_make_db(),
                project_id="proj_1",
                competitors=[{"name": "Cursor", "url": "https://cursor.com"}],
                goals=[],
                data_mode="demo",
            )
        mock_crawl.assert_not_called()
        assert len(result) == 1
        assert result[0].data_source == "demo"

    def test_demo_mode_sources_have_demo_data_source(self):
        from app.agents import collector_agent

        demo_src = _make_source("Cursor", SourceType.pricing_page, data_source="demo")
        with (
            patch.object(collector_agent.crawler_service, "load_demo_fixtures", return_value=[demo_src]),
            patch.object(collector_agent.source_service, "save_sources"),
            patch.object(collector_agent.trace_service, "save_agent_run"),
            patch.object(collector_agent.trace_service, "update_agent_run"),
        ):
            result = collector_agent.run(
                db=_make_db(),
                project_id="proj_1",
                competitors=[{"name": "Cursor", "url": "https://cursor.com"}],
                goals=[],
                data_mode="demo",
            )
        assert all(s.data_source == "demo" for s in result)


class TestCollectorAgentLive:
    def test_live_mode_crawls_pages(self):
        from app.agents import collector_agent

        home_page = _make_page("https://cursor.com", "Cursor Home", "AI IDE")
        pricing_page = _make_page("https://cursor.com/pricing", "Pricing", "$20/month")

        with (
            patch.object(
                collector_agent.source_discovery, "discover_pages",
                return_value=["https://cursor.com", "https://cursor.com/pricing"],
            ),
            patch.object(
                collector_agent.crawler_service, "crawl_page",
                side_effect=[home_page, pricing_page, None, None, None, None, None],
            ),
            patch.object(collector_agent.source_service, "save_sources"),
            patch.object(collector_agent.trace_service, "save_agent_run"),
            patch.object(collector_agent.trace_service, "update_agent_run"),
            patch.object(collector_agent.settings, "enable_live_search", False),
        ):
            result = collector_agent.run(
                db=_make_db(),
                project_id="proj_1",
                competitors=[{"name": "Cursor", "url": "https://cursor.com"}],
                goals=[],
                data_mode="live_with_fallback",
            )

        assert len(result) >= 2
        assert all(s.data_source == "live" for s in result)

    def test_live_mode_no_fallback_when_coverage_sufficient(self):
        from app.agents import collector_agent

        pages = [
            _make_page("https://cursor.com", "Home", "IDE for AI"),
            _make_page("https://cursor.com/pricing", "Pricing", "$20/month"),
            _make_page("https://cursor.com/docs", "Docs", "documentation guide"),
        ]

        # Provide enough None fallbacks for any extra URL candidates the agent may discover
        crawl_side_effect = list(pages) + [None] * 10

        with (
            patch.object(
                collector_agent.source_discovery, "discover_pages",
                return_value=[p.url for p in pages],
            ),
            patch.object(collector_agent.crawler_service, "crawl_page", side_effect=crawl_side_effect),
            patch.object(collector_agent.crawler_service, "load_demo_fixtures") as mock_demo,
            patch.object(collector_agent.source_service, "save_sources"),
            patch.object(collector_agent.trace_service, "save_agent_run"),
            patch.object(collector_agent.trace_service, "update_agent_run"),
            patch.object(collector_agent.settings, "enable_live_search", False),
        ):
            result = collector_agent.run(
                db=_make_db(),
                project_id="proj_1",
                competitors=[{"name": "Cursor", "url": "https://cursor.com"}],
                goals=[],
                data_mode="live_with_fallback",
            )

        # All sources should be live; demo fixtures not loaded for fallback
        live_sources = [s for s in result if s.data_source == "live"]
        assert len(live_sources) >= len(pages)
        mock_demo.assert_not_called()

    def test_live_mode_falls_back_when_all_crawls_fail(self):
        from app.agents import collector_agent

        demo_src = _make_source("Cursor", SourceType.official_website, data_source="demo")

        with (
            patch.object(
                collector_agent.source_discovery, "discover_pages",
                return_value=["https://cursor.com", "https://cursor.com/pricing"],
            ),
            patch.object(collector_agent.crawler_service, "crawl_page", return_value=None),
            patch.object(
                collector_agent.crawler_service, "fixture_exists",
                return_value=True,
            ),
            patch.object(
                collector_agent.crawler_service, "load_demo_fixtures",
                return_value=[demo_src],
            ),
            patch.object(collector_agent.source_service, "save_sources"),
            patch.object(collector_agent.trace_service, "save_agent_run"),
            patch.object(collector_agent.trace_service, "update_agent_run") as mock_update,
        ):
            result = collector_agent.run(
                db=_make_db(),
                project_id="proj_1",
                competitors=[{"name": "Cursor", "url": "https://cursor.com"}],
                goals=[],
                data_mode="live_with_fallback",
            )

        # Should have fallback demo sources
        assert any(s.data_source == "demo" for s in result)
        # Trace output should record fallback_used=True per competitor
        call_kwargs = mock_update.call_args[1]
        cursor_stats = call_kwargs["output"]["collection_stats_by_competitor"]["Cursor"]
        assert cursor_stats["fallback_used"] is True
        assert cursor_stats["fallback_attempted"] is True

    def test_save_sources_receives_data_source_field(self):
        from app.agents import collector_agent

        home_page = _make_page("https://cursor.com", "Home", "AI IDE homepage")
        pricing_page = _make_page("https://cursor.com/pricing", "Pricing", "$20/month per user")
        docs_page = _make_page("https://cursor.com/docs", "Docs", "documentation")

        saved_sources: list = []

        def capture_save(db, project_id, sources):
            saved_sources.extend(sources)
            return []

        # Provide extra None returns so any additional URL candidates don't raise StopIteration
        crawl_side_effect = [home_page, pricing_page, docs_page] + [None] * 10

        with (
            patch.object(
                collector_agent.source_discovery, "discover_pages",
                return_value=[home_page.url, pricing_page.url, docs_page.url],
            ),
            patch.object(
                collector_agent.crawler_service, "crawl_page",
                side_effect=crawl_side_effect,
            ),
            patch.object(collector_agent.source_service, "save_sources", side_effect=capture_save),
            patch.object(collector_agent.trace_service, "save_agent_run"),
            patch.object(collector_agent.trace_service, "update_agent_run"),
            patch.object(collector_agent.settings, "enable_live_search", False),
        ):
            collector_agent.run(
                db=_make_db(),
                project_id="proj_1",
                competitors=[{"name": "Cursor", "url": "https://cursor.com"}],
                goals=[],
                data_mode="live_with_fallback",
            )

        assert len(saved_sources) > 0
        for s in saved_sources:
            assert hasattr(s, "data_source")
            assert s.data_source == "live"
