"""Tests for collector_agent fallback semantics in live_with_fallback mode.

Verifies that:
- fallback_attempted/used/available fields correctly reflect collection outcomes
- demo mode does NOT set fallback fields (only demo_source_count)
- _infer_drop_reason returns human-readable strings for each scenario
"""

from unittest.mock import MagicMock, patch

import pytest

from app.schemas.source import SourceEvidence, SourceType


def _make_db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.models import Base

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _make_source(competitor_name: str, source_type: SourceType) -> SourceEvidence:
    return SourceEvidence(
        project_id="proj_test",
        competitor_id=competitor_name.lower(),
        competitor_name=competitor_name,
        source_type=source_type,
        url=f"https://{competitor_name.lower()}.com",
        title=f"{competitor_name} {source_type}",
        snippet="",
        content="pricing plans available buy now" if source_type == SourceType.pricing_page else "homepage content",
        reliability="high",
        data_source="live",
    )


class TestFallbackAttempted:
    def test_fallback_attempted_when_coverage_below_threshold(self):
        from app.agents import collector_agent

        live_src = _make_source("TestCo", SourceType.official_website)

        with (
            patch.object(
                collector_agent.source_discovery, "discover_pages",
                return_value=["https://testco.com"],
            ),
            patch.object(
                collector_agent.crawler_service, "crawl_page",
                return_value=MagicMock(
                    url="https://testco.com",
                    title="TestCo",
                    snippet="",
                    content="homepage content",
                    status_code=200,
                    robots_status="allowed",
                ),
            ),
            patch.object(
                collector_agent.crawler_service, "fixture_exists", return_value=False
            ),
            patch.object(
                collector_agent.crawler_service, "load_demo_fixtures", return_value=[]
            ),
            patch.object(collector_agent.source_classifier, "classify", return_value=SourceType.official_website),
            patch.object(collector_agent.source_service, "save_sources"),
            patch.object(collector_agent.trace_service, "save_agent_run"),
            patch.object(collector_agent.trace_service, "update_agent_run") as mock_update,
        ):
            collector_agent.run(
                db=_make_db(),
                project_id="proj_1",
                competitors=[{"name": "TestCo", "url": "https://testco.com"}],
                goals=[],
                data_mode="live_with_fallback",
            )

        stats = mock_update.call_args[1]["output"]["collection_stats_by_competitor"]["TestCo"]
        # Homepage only = score 30, below WEAK_THRESHOLD(40) → fallback attempted
        assert stats["fallback_attempted"] is True


class TestFallbackAvailability:
    def test_fallback_used_false_when_no_fixture_exists(self):
        from app.agents import collector_agent

        with (
            patch.object(
                collector_agent.source_discovery, "discover_pages",
                return_value=["https://testco.com"],
            ),
            patch.object(collector_agent.crawler_service, "crawl_page", return_value=None),
            patch.object(
                collector_agent.crawler_service, "fixture_exists", return_value=False
            ),
            patch.object(
                collector_agent.crawler_service, "load_demo_fixtures", return_value=[]
            ),
            patch.object(collector_agent.source_service, "save_sources"),
            patch.object(collector_agent.trace_service, "save_agent_run"),
            patch.object(collector_agent.trace_service, "update_agent_run") as mock_update,
        ):
            collector_agent.run(
                db=_make_db(),
                project_id="proj_1",
                competitors=[{"name": "TestCo", "url": "https://testco.com"}],
                goals=[],
                data_mode="live_with_fallback",
            )

        stats = mock_update.call_args[1]["output"]["collection_stats_by_competitor"]["TestCo"]
        assert stats["fallback_available"] is False
        assert stats["fallback_used"] is False

    def test_fallback_used_true_when_fixture_exists_and_coverage_weak(self):
        from app.agents import collector_agent

        demo_src = _make_source("TestCo", SourceType.pricing_page)
        demo_src.data_source = "demo"

        with (
            patch.object(
                collector_agent.source_discovery, "discover_pages",
                return_value=["https://testco.com"],
            ),
            patch.object(collector_agent.crawler_service, "crawl_page", return_value=None),
            patch.object(
                collector_agent.crawler_service, "fixture_exists", return_value=True
            ),
            patch.object(
                collector_agent.crawler_service, "load_demo_fixtures",
                return_value=[demo_src],
            ),
            patch.object(collector_agent.source_service, "save_sources"),
            patch.object(collector_agent.trace_service, "save_agent_run"),
            patch.object(collector_agent.trace_service, "update_agent_run") as mock_update,
        ):
            collector_agent.run(
                db=_make_db(),
                project_id="proj_1",
                competitors=[{"name": "TestCo", "url": "https://testco.com"}],
                goals=[],
                data_mode="live_with_fallback",
            )

        stats = mock_update.call_args[1]["output"]["collection_stats_by_competitor"]["TestCo"]
        assert stats["fallback_available"] is True
        assert stats["fallback_used"] is True


class TestDemoModeNoFallbackFields:
    def test_demo_mode_stats_have_demo_source_count_not_fallback_fields(self):
        from app.agents import collector_agent

        demo_src = _make_source("Cursor", SourceType.official_website)
        demo_src.data_source = "demo"

        with (
            patch.object(
                collector_agent.crawler_service, "load_demo_fixtures",
                return_value=[demo_src],
            ),
            patch.object(collector_agent.source_service, "save_sources"),
            patch.object(collector_agent.trace_service, "save_agent_run"),
            patch.object(collector_agent.trace_service, "update_agent_run") as mock_update,
        ):
            collector_agent.run(
                db=_make_db(),
                project_id="proj_1",
                competitors=[{"name": "Cursor", "url": "https://cursor.com"}],
                goals=[],
                data_mode="demo",
            )

        stats = mock_update.call_args[1]["output"]["collection_stats_by_competitor"]["Cursor"]
        assert "demo_source_count" in stats
        assert stats["demo_source_count"] == 1
        assert "fallback_used" not in stats
        assert "fallback_available" not in stats
        assert "fallback_attempted" not in stats


class TestInferDropReason:
    def test_infer_drop_reason_no_demo_fallback_available(self):
        from app.agents.collector_agent import _infer_drop_reason

        stats = {"fallback_attempted": True, "fallback_available": False}
        reason = _infer_drop_reason(stats, "live_with_fallback")
        assert reason == "No demo fallback available"

    def test_infer_drop_reason_demo_mode_no_fixture(self):
        from app.agents.collector_agent import _infer_drop_reason

        stats = {"demo_source_count": 0, "source_count": 0}
        reason = _infer_drop_reason(stats, "demo")
        assert reason == "No demo fixture found"
