"""Tests for source_classifier.classify."""

from app.schemas.source import SourceType
from app.services.source_classifier import classify


class TestClassify:
    def test_pricing_url(self):
        assert classify("https://example.com/pricing", "", "") == SourceType.pricing_page

    def test_price_url(self):
        assert classify("https://example.com/price", "", "") == SourceType.pricing_page

    def test_plans_url(self):
        assert classify("https://example.com/plans", "", "") == SourceType.pricing_page

    def test_features_url(self):
        assert classify("https://example.com/features", "", "") == SourceType.features_page

    def test_docs_url(self):
        assert classify("https://example.com/docs", "", "") == SourceType.docs

    def test_documentation_url(self):
        assert classify("https://example.com/documentation", "", "") == SourceType.docs

    def test_api_url(self):
        assert classify("https://example.com/api/v2", "", "") == SourceType.docs

    def test_security_url(self):
        assert classify("https://example.com/security", "", "") == SourceType.security

    def test_privacy_url(self):
        assert classify("https://example.com/privacy", "", "") == SourceType.privacy

    def test_root_url(self):
        assert classify("https://example.com", "", "") == SourceType.official_website

    def test_root_url_with_slash(self):
        assert classify("https://example.com/", "", "") == SourceType.official_website

    def test_content_keyword_pricing(self):
        content = "Our plans start at $10 per month per user subscription"
        result = classify("https://example.com/about", "", content)
        assert result == SourceType.pricing_page

    def test_content_keyword_docs(self):
        content = "Welcome to the documentation API reference getting started guide"
        result = classify("https://example.com/", "", content)
        # Root path wins over content signal
        assert result == SourceType.official_website

    def test_content_keyword_docs_on_unknown_path(self):
        content = "documentation API reference getting started"
        result = classify("https://example.com/help", "", content)
        assert result == SourceType.docs

    def test_default_unknown(self):
        assert classify("https://example.com/blog/post-1", "", "just a blog post") == SourceType.unknown

    def test_url_priority_over_content_when_content_empty(self):
        # Empty content → trust URL path (backward-compat for tests without crawled content)
        result = classify("https://example.com/pricing", "", "")
        assert result == SourceType.pricing_page

    def test_pricing_url_with_non_matching_content_classifies_as_unknown(self):
        # Non-empty content that has no pricing keywords → downgrade to unknown
        result = classify("https://example.com/pricing", "", "documentation reference")
        assert result == SourceType.unknown

    # --- Content-validation tests (TDD: will fail before implementation) ---

    def test_pricing_url_with_discord_title_classifies_as_unknown(self):
        result = classify(
            "https://windsurf.com/pricing",
            "Discord",
            "Join the Windsurf community on Discord",
        )
        assert result == SourceType.unknown

    def test_features_url_with_cloudflare_title_classifies_as_unknown(self):
        result = classify(
            "https://example.com/features",
            "Just a moment...",
            "Checking your browser before accessing",
        )
        assert result == SourceType.unknown

    def test_pricing_url_with_valid_content_classifies_as_pricing_page(self):
        result = classify(
            "https://example.com/pricing",
            "Pricing Plans",
            "Start free, $10/mo Pro plan, enterprise subscription available",
        )
        assert result == SourceType.pricing_page

    def test_docs_url_with_valid_content_classifies_as_docs(self):
        result = classify(
            "https://example.com/docs",
            "Getting Started",
            "API reference and quickstart guide, full SDK documentation",
        )
        assert result == SourceType.docs
