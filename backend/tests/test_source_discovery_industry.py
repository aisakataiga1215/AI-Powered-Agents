"""Tests for industry-specific source discovery paths."""

import pytest

from app.services.source_discovery import (
    CANDIDATE_PATHS,
    _INDUSTRY_MAX_PAGES,
    _INDUSTRY_PATHS,
    discover_pages,
)


class TestIndustryPaths:
    def test_ecommerce_paths_include_seller_and_transactional(self):
        paths = _INDUSTRY_PATHS["ecommerce"]
        for expected in ("/seller", "/seller-fees", "/shipping", "/returns"):
            assert expected in paths, f"ecommerce paths missing {expected}"

    def test_ecommerce_paths_ordered_by_analysis_value(self):
        paths = _INDUSTRY_PATHS["ecommerce"]
        seller_idx = paths.index("/seller")
        help_idx = paths.index("/help")
        assert seller_idx < help_idx, "/seller should come before /help"

    def test_local_services_paths_include_partner_and_driver(self):
        paths = _INDUSTRY_PATHS["local_services"]
        for expected in ("/merchant", "/dasher", "/delivery", "/membership", "/fees"):
            assert expected in paths, f"local_services paths missing {expected}"

    def test_ai_saas_paths_include_enterprise_and_integrations(self):
        paths = _INDUSTRY_PATHS["ai_saas"]
        for expected in ("/pricing", "/enterprise", "/integrations"):
            assert expected in paths, f"ai_saas paths missing {expected}"

    def test_ai_search_paths_include_answer_engine_pages(self):
        paths = _INDUSTRY_PATHS["ai_search"]
        for expected in ("/pricing", "/pro", "/api", "/docs", "/privacy"):
            assert expected in paths, f"ai_search paths missing {expected}"

    def test_design_tool_paths_include_templates_and_enterprise(self):
        paths = _INDUSTRY_PATHS["design_tools"]
        for expected in ("/pricing", "/templates", "/enterprise", "/teams"):
            assert expected in paths, f"design_tools paths missing {expected}"

    def test_open_source_paths_include_nonprofit_context(self):
        paths = _INDUSTRY_PATHS["open_source"]
        for expected in ("/mission", "/community", "/membership", "/donate"):
            assert expected in paths, f"open_source paths missing {expected}"

    def test_unknown_industry_type_falls_back_to_general_no_crash(self):
        urls = discover_pages("https://example.com", industry_type="unknown_industry")
        assert isinstance(urls, list)
        assert len(urls) > 0


class TestIndustryMaxPages:
    def test_ecommerce_max_pages_is_8(self):
        assert _INDUSTRY_MAX_PAGES["ecommerce"] == 8

    def test_local_services_max_pages_is_8(self):
        assert _INDUSTRY_MAX_PAGES["local_services"] == 8

    def test_ai_saas_max_pages_is_5(self):
        assert _INDUSTRY_MAX_PAGES["ai_saas"] == 5

    def test_general_max_pages_is_5(self):
        assert _INDUSTRY_MAX_PAGES["general"] == 5

    def test_new_industry_max_pages_are_8(self):
        assert _INDUSTRY_MAX_PAGES["ai_search"] == 8
        assert _INDUSTRY_MAX_PAGES["design_tools"] == 8
        assert _INDUSTRY_MAX_PAGES["open_source"] == 8

    def test_explicit_max_pages_respected_over_industry_default(self):
        urls = discover_pages("https://example.com", max_pages=3, industry_type="ecommerce")
        assert len(urls) <= 3

    def test_ecommerce_uses_8_by_default(self):
        urls = discover_pages("https://example.com", industry_type="ecommerce")
        # ecommerce has 14 candidate paths + homepage = 15 total, default max is 8
        assert len(urls) == 8

    def test_ai_saas_uses_5_by_default(self):
        urls = discover_pages("https://example.com", industry_type="ai_saas")
        assert len(urls) == 5


class TestCandidatePathsBackwardCompat:
    def test_candidate_paths_is_ai_saas_alias(self):
        assert set(CANDIDATE_PATHS) == set(_INDUSTRY_PATHS["ai_saas"])

    def test_candidate_paths_importable(self):
        from app.services.source_discovery import CANDIDATE_PATHS as cp
        assert isinstance(cp, list)
        assert len(cp) > 0
