"""API tests for M15A search routes (/api/search/sources) and M15B (/api/search/competitors)."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)


class TestSearchSourcesEndpoint:
    def test_returns_candidates_with_mocked_service(self, client):
        from app.schemas.search import CandidateSource
        from app.schemas.source import SourceType

        fake_candidate = CandidateSource(
            competitor_name="Cursor",
            url="https://cursor.com/pricing",
            title="Cursor Pricing",
            snippet="$20/month",
            suggested_source_type=SourceType.pricing_page,
            confidence="high",
            reason="Pricing page",
        )

        with (
            patch("app.api.routes.search.SearchService") as MockSvc,
            patch("app.api.routes.search._search_configured", return_value=True),
        ):
            mock_instance = MockSvc.return_value
            mock_instance.search_sources.return_value = [fake_candidate]

            resp = client.post("/api/search/sources", json={
                "competitor_name": "Cursor",
                "website": "https://cursor.com",
                "goals": ["pricing_analysis"],
                "industry_type": "ai_saas",
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["search_available"] is True
        assert len(body["candidates"]) == 1
        assert body["candidates"][0]["url"] == "https://cursor.com/pricing"
        assert body["candidates"][0]["selected_by_default"] is False

    def test_search_available_false_when_unconfigured(self, client):
        with patch("app.api.routes.search._search_configured", return_value=False):
            resp = client.post("/api/search/sources", json={
                "competitor_name": "Cursor",
                "website": "https://cursor.com",
                "goals": [],
                "industry_type": "general",
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["search_available"] is False

    def test_returns_422_for_empty_competitor_name(self, client):
        resp = client.post("/api/search/sources", json={
            "competitor_name": "  ",
            "website": "https://cursor.com",
        })
        assert resp.status_code == 422

    def test_returns_422_for_invalid_website_url(self, client):
        resp = client.post("/api/search/sources", json={
            "competitor_name": "Cursor",
            "website": "not-a-url",
        })
        assert resp.status_code == 422


class TestDiscoverCompetitorsEndpoint:
    def test_discover_competitors_endpoint_returns_candidates(self, client):
        from app.schemas.discovery import CandidateCompetitor

        fake_candidate = CandidateCompetitor(
            name="Cursor",
            website="https://cursor.com",
            raw_title="Cursor – AI Code Editor",
            source_url="https://cursor.com/",
            domain="cursor.com",
            relevance_score=80,
            relevance_reason="appears to be a product/company",
        )

        with (
            patch("app.api.routes.search.SearchService") as MockSvc,
            patch("app.api.routes.search._search_configured", return_value=True),
        ):
            mock_instance = MockSvc.return_value
            mock_instance.discover_competitors.return_value = [fake_candidate]

            resp = client.post("/api/search/competitors", json={
                "industry": "AI Coding Tools",
                "industry_type": "ai_saas",
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["search_available"] is True
        assert len(body["candidates"]) == 1
        assert body["candidates"][0]["name"] == "Cursor"
        assert body["candidates"][0]["source_url"] == "https://cursor.com/"
        assert body["candidates"][0]["relevance_score"] == 80

    def test_discover_competitors_search_unavailable_when_unconfigured(self, client):
        with patch("app.api.routes.search._search_configured", return_value=False):
            resp = client.post("/api/search/competitors", json={
                "industry": "AI Coding Tools",
                "industry_type": "general",
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["search_available"] is False

    def test_discover_competitors_returns_422_for_empty_industry(self, client):
        resp = client.post("/api/search/competitors", json={
            "industry": "  ",
        })
        assert resp.status_code == 422
