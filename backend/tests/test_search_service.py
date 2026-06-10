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


# ---------------------------------------------------------------------------
# TestSearchSources (M15A)
# ---------------------------------------------------------------------------


class TestSearchSources:
    def _make_service(self, results: list):
        from app.services.search_provider import SearchResult
        from app.services.search_service import SearchService

        mock_provider = MagicMock()
        mock_provider.search.return_value = [
            SearchResult(url=r["url"], title=r.get("title", ""), snippet=r.get("snippet", ""))
            for r in results
        ]
        return SearchService(mock_provider)

    def test_search_sources_returns_candidates(self):
        svc = self._make_service([
            {"url": "https://cursor.com/pricing", "title": "Cursor Pricing"},
            {"url": "https://cursor.com/docs", "title": "Cursor Docs"},
        ])
        candidates = svc.search_sources("Cursor", "https://cursor.com", ["pricing_analysis"])
        assert len(candidates) >= 1
        assert all(hasattr(c, "url") for c in candidates)
        assert all(hasattr(c, "snippet") for c in candidates)
        assert all(c.selected_by_default is False for c in candidates)

    def test_search_sources_null_provider_returns_empty(self):
        from app.services.search_provider import NullSearchProvider
        from app.services.search_service import SearchService

        svc = SearchService(NullSearchProvider())
        candidates = svc.search_sources("Cursor", "https://cursor.com", [])
        assert candidates == []

    def test_search_sources_applies_blocked_domain_filter(self):
        svc = self._make_service([
            {"url": "https://youtube.com/watch?v=abc", "title": "YouTube"},
            {"url": "https://cursor.com/pricing", "title": "Cursor Pricing"},
        ])
        candidates = svc.search_sources("Cursor", "https://cursor.com", [])
        urls = [c.url for c in candidates]
        assert not any("youtube.com" in u for u in urls)
        assert any("cursor.com/pricing" in u for u in urls)

    def test_search_sources_deduplicates_by_normalized_url(self):
        svc = self._make_service([
            {"url": "https://cursor.com/pricing", "title": "Pricing"},
            {"url": "https://cursor.com/pricing/", "title": "Pricing Trailing Slash"},
        ])
        candidates = svc.search_sources("Cursor", "https://cursor.com", [])
        urls_normalized = [c.url.rstrip("/").lower() for c in candidates]
        assert len(set(urls_normalized)) == len(urls_normalized)

    def test_search_sources_handles_per_query_error(self):
        from app.services.search_provider import SearchResult
        from app.services.search_service import SearchService

        call_count = 0

        def side_effect(query, max_results=3, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Tavily timeout")
            return [SearchResult(url="https://cursor.com/features", title="Features", snippet="")]

        mock_provider = MagicMock()
        mock_provider.search.side_effect = side_effect
        svc = SearchService(mock_provider)

        candidates = svc.search_sources("Cursor", "https://cursor.com", ["pricing_analysis"])
        # Error in first query should not crash — remaining queries yield results
        assert isinstance(candidates, list)

    def test_search_sources_skips_third_party_core_sources_in_general_pass(self):
        from app.services.search_provider import SearchResult
        from app.services.search_service import SearchService

        mock_provider = MagicMock()
        mock_provider.search.side_effect = [
            [],
            [],
            [
                SearchResult(
                    url="https://psycopg.org/docs/cursor.html",
                    title="The cursor class",
                    snippet="Database cursor documentation",
                ),
                SearchResult(
                    url="https://cursor.com/docs/agent/overview",
                    title="Overview | Cursor Docs",
                    snippet="Cursor Agent documentation",
                ),
            ],
            [],
        ]
        svc = SearchService(mock_provider)

        candidates = svc.search_sources("Cursor", "https://cursor.com", ["user_personas"])
        urls = [c.url for c in candidates]
        assert "https://psycopg.org/docs/cursor.html" not in urls
        assert "https://cursor.com/docs/agent/overview" in urls

    def test_search_sources_uses_alias_domains_for_confidence(self):
        from app.services.search_provider import SearchResult
        from app.services.search_service import SearchService

        mock_provider = MagicMock()
        mock_provider.search.return_value = [
            SearchResult(
                url="https://docs.trae.ai/ide/set-up-trae",
                title="Trae setup guide",
                snippet="Getting started with Trae",
            )
        ]
        svc = SearchService(mock_provider)

        candidates = svc.search_sources("Trae", "https://www.trae.ai", ["user_personas"])
        assert candidates
        assert candidates[0].confidence == "high"


# ---------------------------------------------------------------------------
# TestDiscoverCompetitors (M15B)
# ---------------------------------------------------------------------------


class TestDiscoverCompetitors:
    def _make_service(self, results: list):
        from app.services.search_provider import SearchResult
        from app.services.search_service import SearchService

        mock_provider = MagicMock()
        mock_provider.search.return_value = [
            SearchResult(url=r["url"], title=r.get("title", ""), snippet=r.get("snippet", ""))
            for r in results
        ]
        return SearchService(mock_provider)

    def test_discover_competitors_returns_candidates(self):
        svc = self._make_service([
            {"url": "https://cursor.com/", "title": "Cursor – AI Code Editor", "snippet": "An AI-first IDE."},
            {"url": "https://github.com/features/copilot", "title": "GitHub Copilot", "snippet": "AI pair programmer."},
        ])
        candidates = svc.discover_competitors("AI Coding Tools", "ai_saas")
        assert len(candidates) >= 1
        assert all(hasattr(c, "name") for c in candidates)
        assert all(hasattr(c, "website") for c in candidates)
        assert all(hasattr(c, "relevance_score") for c in candidates)

    def test_discover_competitors_extracts_known_products_from_listicles(self):
        svc = self._make_service([
            {
                "url": "https://zapier.com/blog/ai-coding-tools",
                "title": "The best AI coding tools",
                "snippet": "Cursor, GitHub Copilot, Windsurf, Tabnine, and Qodo are leading options.",
            },
        ])
        candidates = svc.discover_competitors("AI Coding Tools", "ai_saas")
        names = {c.name for c in candidates}
        assert {"Cursor", "GitHub Copilot", "Windsurf", "Tabnine", "Qodo"} <= names
        assert not any(c.domain == "zapier.com" for c in candidates)

    def test_discover_competitors_extracts_known_social_products_from_listicles(self):
        svc = self._make_service([
            {
                "url": "https://example.com/best-dating-apps",
                "title": "Best dating apps",
                "snippet": "Compare Tinder, Bumble, Hinge, OkCupid, and Badoo.",
            },
        ])
        candidates = svc.discover_competitors("dating apps", "social")
        names = {c.name for c in candidates}
        assert {"Tinder", "Bumble", "Hinge"} <= names
        assert not any(c.domain == "example.com" for c in candidates)

    def test_industry_vendor_names_are_not_competitors(self):
        from app.services.search_service import _score_competitor_relevance

        score, reason = _score_competitor_relevance(
            "Dating App Development Company",
            "Dating App Development Company",
            "https://vendor.example.com",
            "vendor.example.com",
            "dating app official website",
            "social",
        )
        assert score < 60
        assert "vendor" in reason

    def test_ecommerce_site_builders_are_not_marketplace_competitors(self):
        from app.services.search_service import _score_competitor_relevance

        score, reason = _score_competitor_relevance(
            "Creazione del negozio online",
            "Creazione del negozio online",
            "https://godaddy.com/it-it/siti-web/negozio-online",
            "godaddy.com",
            "online marketplaces official ecommerce platform",
            "ecommerce",
        )
        assert score < 60
        assert "not a direct" in reason or "vendor" in reason

    def test_discover_competitors_null_provider_returns_empty(self):
        from app.services.search_provider import NullSearchProvider
        from app.services.search_service import SearchService

        svc = SearchService(NullSearchProvider())
        candidates = svc.discover_competitors("AI Coding Tools")
        assert candidates == []

    def test_discover_competitors_deduplicates_by_domain(self):
        svc = self._make_service([
            {"url": "https://cursor.com/pricing", "title": "Cursor Pricing"},
            {"url": "https://cursor.com/about", "title": "Cursor About"},
        ])
        candidates = svc.discover_competitors("AI Coding Tools", "ai_saas")
        domains = [c.domain for c in candidates]
        assert len(set(domains)) == len(domains), "Each domain should appear at most once"

    def test_discover_competitors_filters_discovery_blocked_domains(self):
        svc = self._make_service([
            {"url": "https://g2.com/categories/ai-coding", "title": "Top AI Coding Tools on G2"},
            {"url": "https://capterra.com/software/ai", "title": "Best AI Tools - Capterra"},
            {"url": "https://cursor.com/", "title": "Cursor – AI Code Editor"},
        ])
        candidates = svc.discover_competitors("AI Coding Tools", "ai_saas")
        urls = [c.source_url for c in candidates]
        assert not any("g2.com" in u for u in urls)
        assert not any("capterra.com" in u for u in urls)

    def test_discover_competitors_filters_listicle_titles(self):
        svc = self._make_service([
            {"url": "https://somesite.com/article", "title": "Top 10 AI Coding Tools 2025"},
        ])
        candidates = svc.discover_competitors("AI Coding Tools", "ai_saas")
        listicle_candidates = [c for c in candidates if c.source_url == "https://somesite.com/article"]
        for c in listicle_candidates:
            assert c.relevance_score <= 15, f"Listicle should score ≤15, got {c.relevance_score}"

    def test_discover_competitors_preserves_raw_title_and_source_url(self):
        original_title = "Cursor – The AI-First Code Editor"
        original_url = "https://cursor.com/features/ai"
        svc = self._make_service([
            {"url": original_url, "title": original_title, "snippet": "Write code faster."},
        ])
        candidates = svc.discover_competitors("AI Coding Tools", "ai_saas")
        assert len(candidates) >= 1
        c = candidates[0]
        assert c.raw_title == original_title
        assert c.source_url == original_url

    def test_discover_competitors_handles_per_query_error(self):
        from app.services.search_provider import SearchResult
        from app.services.search_service import SearchService

        call_count = 0

        def side_effect(query, max_results=5, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Tavily rate limit")
            return [SearchResult(url="https://cursor.com/", title="Cursor", snippet="")]

        mock_provider = MagicMock()
        mock_provider.search.side_effect = side_effect
        svc = SearchService(mock_provider)

        candidates = svc.discover_competitors("AI Coding Tools", "ai_saas")
        assert isinstance(candidates, list)  # no crash; partial results OK

    def test_discover_competitors_social_queries_include_social_templates(self):
        from app.services.search_service import _DISCOVERY_TEMPLATES

        social_templates = _DISCOVERY_TEMPLATES.get("social", [])
        queries_lower = [t.lower() for t in social_templates]
        assert any("dating" in q for q in queries_lower), "social templates should include dating"
        assert any("tinder" in q or "bumble" in q for q in queries_lower), (
            "social templates should reference known social apps"
        )

    def test_discover_competitors_handles_blog_subdomains_across_categories(self):
        for industry, industry_type in [
            ("online store builders", "ecommerce"),
            ("food delivery", "local_services"),
            ("creator social platforms", "social"),
            ("project management software", "general"),
        ]:
            svc = self._make_service([
                {"url": "https://blog.stuart.com/delivery-platforms", "title": "Delivery Platforms"},
                {"url": "https://exampleproduct.com/", "title": "Example Product"},
            ])
            candidates = svc.discover_competitors(industry, industry_type)
            assert not any(c.domain == "blog.stuart.com" for c in candidates)

    def test_discover_competitors_filters_research_and_app_store_domains(self):
        svc = self._make_service([
            {"url": "https://mordorintelligence.com/industry-reports/project-management-software-market", "title": "Project Management Software Market Size"},
            {"url": "https://marketsandmarkets.com/Market-Reports/project-management-software-market", "title": "Project Management Market Report"},
            {"url": "https://apps.apple.com/us/app/postmates/id512393983", "title": "Postmates on the App Store"},
            {"url": "https://play.google.com/store/apps/details?id=com.example", "title": "Example App"},
            {"url": "https://openproject.org/", "title": "OpenProject"},
        ])
        candidates = svc.discover_competitors("project management software", "general")
        domains = {c.domain for c in candidates}
        assert "mordorintelligence.com" not in domains
        assert "marketsandmarkets.com" not in domains
        assert "apps.apple.com" not in domains
        assert "play.google.com" not in domains

    def test_discover_competitors_caps_root_level_listicle_paths(self):
        from app.services.search_service import _score_competitor_relevance

        for url in [
            "https://example.com/best-shopping-apps",
            "https://example.com/market-size-project-management",
            "https://example.com/ai-tools-review",
            "https://example.com/alternatives-to-asana",
        ]:
            score, _ = _score_competitor_relevance(
                "Example",
                "Example Product",
                url,
                "example.com",
                "project management software official software",
                industry_type="general",
            )
            assert score <= 30

    def test_discover_competitors_keeps_positive_homepages_across_categories(self):
        for industry, industry_type, url, title in [
            ("online store builders", "ecommerce", "https://shopify.com/", "Shopify"),
            ("food delivery", "local_services", "https://doordash.com/", "DoorDash"),
            ("creator social platforms", "social", "https://creatoriq.com/", "CreatorIQ"),
            ("project management software", "general", "https://asana.com/", "Asana"),
        ]:
            svc = self._make_service([{"url": url, "title": title}])
            candidates = svc.discover_competitors(industry, industry_type)
            assert candidates, f"{industry_type} homepage should remain discoverable"
            assert candidates[0].relevance_score >= 60

    def test_non_dating_social_query_does_not_use_dating_templates(self):
        from app.services.search_provider import SearchResult
        from app.services.search_service import SearchService

        queries: list[str] = []

        def search(query, max_results=5, **kwargs):
            queries.append(query)
            return [SearchResult(url="https://creatoriq.com/", title="CreatorIQ", snippet="")]

        mock_provider = MagicMock()
        mock_provider.search.side_effect = search
        svc = SearchService(mock_provider)
        svc.discover_competitors("creator social platforms", "social")

        joined = " ".join(queries).lower()
        assert "dating" not in joined
        assert "tinder" not in joined
        assert "bumble" not in joined

    def test_social_dating_query_keeps_dating_templates(self):
        from app.services.search_provider import SearchResult
        from app.services.search_service import SearchService

        queries: list[str] = []

        def search(query, max_results=5, **kwargs):
            queries.append(query)
            return [SearchResult(url="https://hinge.co/", title="Hinge", snippet="")]

        mock_provider = MagicMock()
        mock_provider.search.side_effect = search
        svc = SearchService(mock_provider)
        svc.discover_competitors("dating apps", "social")

        joined = " ".join(queries).lower()
        assert "dating" in joined
        assert "tinder" in joined or "bumble" in joined


# ---------------------------------------------------------------------------
# TestDiscoverCompetitorsQuality (M16.1 regression)
# ---------------------------------------------------------------------------


class TestDiscoverCompetitorsQuality:
    def _make_service(self, results: list):
        from app.services.search_provider import SearchResult
        from app.services.search_service import SearchService

        mock_provider = MagicMock()
        mock_provider.search.return_value = [
            SearchResult(url=r["url"], title=r.get("title", ""), snippet=r.get("snippet", ""))
            for r in results
        ]
        return SearchService(mock_provider)

    def test_article_path_scores_low_and_is_filtered(self):
        """Blog/article URL paths must score <= 30 and be filtered from results."""
        from app.services.search_service import _score_competitor_relevance

        score, reason = _score_competitor_relevance(
            "DigitalOcean",
            "10 Best AI Coding Tools",
            "https://digitalocean.com/blog/ai-coding-tools",
            "digitalocean.com",
            "AI Coding Tools competitors",
        )
        assert score <= 30, f"Article path should score <= 30, got {score}"
        assert "article" in reason.lower() or "blog" in reason.lower() or "listicle" in reason.lower()

    def test_article_path_filtered_from_discover_results(self):
        """discover_competitors() must not return article-path URLs as candidates."""
        svc = self._make_service([
            {"url": "https://digitalocean.com/blog/ai-tools", "title": "AI Tools Roundup"},
            {"url": "https://cursor.com/", "title": "Cursor – AI Code Editor"},
        ])
        candidates = svc.discover_competitors("AI Coding Tools", "ai_saas")
        assert not any("digitalocean.com" in c.domain for c in candidates), (
            "DigitalOcean blog article should be filtered out"
        )

    def test_gartner_blocked_from_discovery(self):
        """Gartner (analyst/research firm) must never appear as a competitor candidate."""
        svc = self._make_service([
            {"url": "https://gartner.com/en/ai-coding", "title": "Gartner AI Coding Hype Cycle"},
        ])
        candidates = svc.discover_competitors("AI Coding Tools", "ai_saas")
        assert not any("gartner.com" in c.domain for c in candidates)

    def test_digitalocean_not_globally_blocked(self):
        """DigitalOcean must NOT be in _DISCOVERY_BLOCKED_DOMAINS; it's a valid cloud competitor."""
        from app.services.search_service import _DISCOVERY_BLOCKED_DOMAINS

        assert "digitalocean.com" not in _DISCOVERY_BLOCKED_DOMAINS

    def test_zapier_not_globally_blocked(self):
        """Zapier must NOT be in _DISCOVERY_BLOCKED_DOMAINS; it's a valid automation competitor."""
        from app.services.search_service import _DISCOVERY_BLOCKED_DOMAINS

        assert "zapier.com" not in _DISCOVERY_BLOCKED_DOMAINS

    def test_product_homepage_scores_at_least_min_score(self):
        """A root product homepage must score >= _DISCOVERY_MIN_SCORE."""
        from app.services.search_service import _DISCOVERY_MIN_SCORE, _score_competitor_relevance

        score, _ = _score_competitor_relevance(
            "Cursor",
            "Cursor – The AI Code Editor",
            "https://cursor.com/",
            "cursor.com",
            "AI Coding Tools competitors",
        )
        assert score >= _DISCOVERY_MIN_SCORE, (
            f"Product homepage should score >= {_DISCOVERY_MIN_SCORE}, got {score}"
        )

    def test_discover_only_returns_min_score_candidates(self):
        """All candidates returned by discover_competitors() must meet _DISCOVERY_MIN_SCORE."""
        from app.services.search_service import _DISCOVERY_MIN_SCORE

        svc = self._make_service([
            {"url": "https://cursor.com/", "title": "Cursor"},
            {"url": "https://somesite.com/blog/ai-tools", "title": "Blog Post About AI Tools"},
        ])
        candidates = svc.discover_competitors("AI Coding Tools", "ai_saas")
        for c in candidates:
            assert c.relevance_score >= _DISCOVERY_MIN_SCORE, (
                f"Candidate {c.name} scored {c.relevance_score} < {_DISCOVERY_MIN_SCORE}"
            )

    def test_discover_results_sorted_descending_by_score(self):
        """discover_competitors() results must be sorted by relevance_score descending."""
        svc = self._make_service([
            {"url": "https://cursor.com/", "title": "Cursor – AI Code Editor"},
            {"url": "https://github.com/features/copilot", "title": "GitHub Copilot"},
            {"url": "https://tabnine.com/", "title": "Tabnine AI"},
        ])
        candidates = svc.discover_competitors("AI Coding Tools", "ai_saas")
        for i in range(len(candidates) - 1):
            assert candidates[i].relevance_score >= candidates[i + 1].relevance_score


# ---------------------------------------------------------------------------
# TestDiscoverCompetitorsM162 (M16.2 regression)
# ---------------------------------------------------------------------------


class TestDiscoverCompetitorsM162:
    def _make_service(self, results: list):
        from app.services.search_provider import SearchResult
        from app.services.search_service import SearchService

        mock_provider = MagicMock()
        mock_provider.search.return_value = [
            SearchResult(url=r["url"], title=r.get("title", ""), snippet=r.get("snippet", ""))
            for r in results
        ]
        return SearchService(mock_provider)

    def test_known_ai_product_homepage_scores_high(self):
        """Known AI coding product homepages must score >= 60 for ai_saas industry."""
        from app.services.search_service import _score_competitor_relevance

        for domain, url in [
            ("cursor.com", "https://cursor.com/"),
            ("tabnine.com", "https://tabnine.com/"),
            ("codeium.com", "https://codeium.com/"),
        ]:
            score, _ = _score_competitor_relevance(
                domain.split(".")[0].title(),
                f"{domain.split('.')[0].title()} – AI Code Editor",
                url,
                domain,
                "AI Coding Tools competitors",
                industry_type="ai_saas",
            )
            assert score >= 60, f"{domain} should score >= 60 for ai_saas, got {score}"

    def test_article_path_scores_at_most_30(self):
        """Article/blog paths must be capped at <= 30 regardless of other signals."""
        from app.services.search_service import _score_competitor_relevance

        for url in [
            "https://digitalocean.com/blog/ai-coding-tools",
            "https://zapier.com/blog/best-ai-coding-tools",
            "https://aimlapi.com/comparisons/ai-coding-assistants",
            "https://apiiro.com/glossary/ai-coding-assistants",
            "https://devgenius.io/blog/top-coding-assistants",
            "https://axify.io/resources/ai-coding-comparison",
        ]:
            parsed = url.split("/")[2].removeprefix("www.")
            score, reason = _score_competitor_relevance(
                parsed.split(".")[0].title(),
                "Best AI Coding Tools 2025",
                url,
                parsed,
                "AI coding tools",
                industry_type="ai_saas",
            )
            assert score <= 30, f"{url} should score <= 30, got {score}"

    def test_listicle_title_scores_at_most_15(self):
        """Titles matching listicle patterns must score <= 15."""
        from app.services.search_service import _score_competitor_relevance

        for title in [
            "Best AI Coding Tools 2025",
            "Top AI Coding Assistants",
            "AI Coding Tools Comparison",
            "I tested 10 AI IDEs so you don't have to",
        ]:
            score, _ = _score_competitor_relevance(
                "SomeSite",
                title,
                "https://somesite.com/article",
                "somesite.com",
                "AI Coding Tools competitors",
                industry_type="ai_saas",
            )
            assert score <= 15, f"Title {title!r} should score <= 15, got {score}"

    def test_min_score_60_filters_marginal_candidates(self):
        """discover_competitors() must only return candidates with score >= 60."""
        from app.services.search_service import _DISCOVERY_MIN_SCORE

        assert _DISCOVERY_MIN_SCORE == 60

        svc = self._make_service([
            {"url": "https://cursor.com/", "title": "Cursor – AI Code Editor"},
            {"url": "https://somesite.com/blog/ai-tools", "title": "Blog Post About AI Tools"},
            {"url": "https://zapier.com/blog/ai-coding", "title": "Best AI Coding Tools"},
        ])
        candidates = svc.discover_competitors("AI Coding Tools", "ai_saas")
        for c in candidates:
            assert c.relevance_score >= 60, (
                f"Candidate {c.name} scored {c.relevance_score} < 60"
            )

    def test_brand_negative_terms_cap_ambiguous_brand(self):
        """A brand name with windsurfing/sport signals and no AI signals should score <= 35."""
        from app.services.search_service import _score_competitor_relevance

        for title in [
            "Windsurf Gear – Premium Windsurfing Equipment",
            "Windsurf Lessons and Sailing Boards",
        ]:
            score, reason = _score_competitor_relevance(
                "Windsurf Gear",
                title,
                "https://windsurfgear.com/",
                "windsurfgear.com",
                "AI Coding Tools competitors",
                industry_type="ai_saas",
            )
            assert score <= 35, f"Windsurfing site should score <= 35, got {score}"
            assert "non-tech" in reason.lower() or "negative" in reason.lower() or "brand" in reason.lower(), reason

    def test_windsurf_ai_domain_not_penalized(self):
        """windsurf.ai (known AI coding product) must not be penalized by negative terms."""
        from app.services.search_service import _score_competitor_relevance

        score, _ = _score_competitor_relevance(
            "Windsurf",
            "Windsurf – AI Code Editor by Codeium",
            "https://windsurf.ai/",
            "windsurf.ai",
            "AI Coding Tools competitors",
            industry_type="ai_saas",
        )
        # Known product in _AI_CODING_PRODUCT_DOMAINS should not be capped
        assert score >= 60, f"windsurf.ai should score >= 60 as a known AI product, got {score}"

    def test_github_openearth_windsurf_low_score(self):
        """github.com/openearth/windsurf (geospatial, not AI IDE) should score low."""
        from app.services.search_service import _score_competitor_relevance

        score, reason = _score_competitor_relevance(
            "Openearth Windsurf",
            "openearth/windsurf: Open-source coastal engineering tools",
            "https://github.com/openearth/windsurf",
            "github.com",
            "AI Coding Tools competitors",
            industry_type="ai_saas",
        )
        # github.com/openearth/windsurf is a deep path — not a product homepage
        # Title mentions windsurfing-adjacent terms without AI signals
        assert score <= 50, f"github.com/openearth/windsurf should not score high, got {score}"


# ---------------------------------------------------------------------------
# TestSourceClassifierM162 (M16.2 source classifier)
# ---------------------------------------------------------------------------


class TestSourceClassifierM162:
    def test_readthedocs_root_not_official_website(self):
        """windsurf.readthedocs.io root must NOT be classified as official_website."""
        from app.services.source_classifier import classify
        from app.schemas.source import SourceType

        result = classify("https://windsurf.readthedocs.io/", "Windsurf Docs", "")
        assert result != SourceType.official_website, (
            "readthedocs.io root should not be official_website"
        )

    def test_readthedocs_docs_path_classified_as_docs(self):
        """readthedocs URL with /docs/ path should be classified as docs, not official_website."""
        from app.services.source_classifier import classify
        from app.schemas.source import SourceType

        result = classify("https://windsurf.readthedocs.io/en/latest/", "Windsurf Documentation", "")
        # Not official_website — it's a third-party host
        assert result != SourceType.official_website

    def test_official_domain_root_is_official_website(self):
        """cursor.com root must still be classified as official_website."""
        from app.services.source_classifier import classify
        from app.schemas.source import SourceType

        result = classify("https://cursor.com/", "Cursor – AI Code Editor", "")
        assert result == SourceType.official_website

    def test_github_pages_not_official_website(self):
        """github.io subdomain root must not be official_website."""
        from app.services.source_classifier import classify
        from app.schemas.source import SourceType

        result = classify("https://openearth.github.io/windsurf/", "Windsurf Docs", "")
        assert result != SourceType.official_website

    def test_windsurf_official_domain_is_official_website(self):
        """windsurf.com root should be classified as official_website."""
        from app.services.source_classifier import classify
        from app.schemas.source import SourceType

        result = classify("https://windsurf.com/", "Windsurf – AI IDE", "")
        assert result == SourceType.official_website

    def test_official_compare_page_is_features_page(self):
        from app.services.source_classifier import classify
        from app.schemas.source import SourceType

        result = classify(
            "https://windsurf.com/compare/windsurf-vs-cursor",
            "Windsurf vs Cursor",
            "Windsurf features and capabilities comparison",
        )
        assert result == SourceType.features_page

    def test_docs_usage_page_can_be_pricing_page(self):
        from app.services.source_classifier import classify
        from app.schemas.source import SourceType

        result = classify(
            "https://docs.windsurf.com/windsurf/accounts/usage",
            "Plans and Usage",
            "Windsurf pricing plans, usage limits, paid plans, and credits",
        )
        assert result == SourceType.pricing_page

    def test_blog_path_is_blog(self):
        from app.services.source_classifier import classify
        from app.schemas.source import SourceType

        result = classify(
            "https://windsurf.com/blog",
            "Blog | Windsurf",
            "Introducing our new Windsurf pricing plans",
        )
        assert result == SourceType.blog

    def test_download_page_footer_pricing_does_not_become_pricing_page(self):
        from app.services.source_classifier import classify
        from app.schemas.source import SourceType

        result = classify(
            "https://cursor.com/download",
            "Cursor · Download",
            "Resources Pricing Docs Download. Pro $20 / mo. Teams $40 / user / mo.",
        )
        assert result == SourceType.unknown

    def test_terms_pricing_policy_is_not_primary_pricing_page(self):
        from app.services.source_classifier import classify
        from app.schemas.source import SourceType

        result = classify(
            "https://cursor.com/terms/pricing",
            "Cursor · Pricing Policy",
            "Fees, rates and pricing applicable to Cursor services.",
        )
        assert result == SourceType.unknown

    def test_product_page_with_pricing_footer_is_not_pricing_page(self):
        from app.services.source_classifier import classify
        from app.schemas.source import SourceType

        result = classify(
            "https://www.trae.ai/solo",
            "Trae SOLO",
            "Pricing Plans Enterprise Free Pro",
        )
        assert result == SourceType.unknown


# ---------------------------------------------------------------------------
# TestSourceConfidenceM162 (M16.2 source confidence inference)
# ---------------------------------------------------------------------------


class TestSourceConfidenceM162:
    def test_readthedocs_not_high_confidence(self):
        """windsurf.readthedocs.io must not be 'high' confidence for Windsurf's official site."""
        from app.services.search_service import _infer_source_confidence

        confidence = _infer_source_confidence(
            "official_website",
            "https://windsurf.readthedocs.io/",
            "https://windsurf.ai",
        )
        assert confidence != "high", (
            "readthedocs.io should not be high confidence for official_website"
        )

    def test_official_domain_source_is_high_confidence(self):
        """cursor.com/pricing must be 'high' confidence when competitor site is cursor.com."""
        from app.services.search_service import _infer_source_confidence

        confidence = _infer_source_confidence(
            "pricing_page",
            "https://cursor.com/pricing",
            "https://cursor.com",
        )
        assert confidence == "high"

    def test_unlisted_forum_subdomain_is_not_high_confidence(self):
        """Only explicitly allowed official aliases should be high-confidence sources."""
        from app.services.search_service import _infer_source_confidence, _is_official_url

        official_domains = ["cursor.com", "docs.cursor.com"]

        assert not _is_official_url("https://forum.cursor.com/t/docs/123", official_domains)
        confidence = _infer_source_confidence(
            "docs",
            "https://forum.cursor.com/t/docs/123",
            "https://cursor.com",
            official_domains,
        )
        assert confidence == "medium"

    def test_third_party_review_site_is_low_confidence(self):
        """A review/unknown source not on the official domain must be low confidence."""
        from app.services.search_service import _infer_source_confidence

        confidence = _infer_source_confidence(
            "review",
            "https://blog.example.com/windsurf-review",
            "https://windsurf.ai",
        )
        assert confidence == "low"
