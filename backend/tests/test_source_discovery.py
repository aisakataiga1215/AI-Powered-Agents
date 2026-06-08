"""Tests for source_discovery.discover_pages."""

from app.services.source_discovery import CANDIDATE_PATHS, discover_pages


class TestDiscoverPages:
    def test_includes_homepage(self):
        urls = discover_pages("https://cursor.sh")
        assert urls[0] == "https://cursor.sh"

    def test_returns_same_domain_urls(self):
        urls = discover_pages("https://cursor.sh", max_pages=10)
        for url in urls:
            assert url.startswith("https://cursor.sh")

    def test_respects_max_pages(self):
        urls = discover_pages("https://cursor.sh", max_pages=3)
        assert len(urls) <= 3

    def test_default_max_is_five(self):
        urls = discover_pages("https://cursor.sh")
        assert len(urls) <= 5

    def test_no_duplicates(self):
        urls = discover_pages("https://cursor.sh", max_pages=20)
        assert len(urls) == len(set(urls))

    def test_includes_candidate_paths(self):
        urls = discover_pages("https://example.com", max_pages=len(CANDIDATE_PATHS) + 1)
        expected = {f"https://example.com{p}" for p in CANDIDATE_PATHS}
        found = set(urls[1:])  # skip homepage
        # At least some candidate paths should appear
        assert len(found & expected) > 0

    def test_returns_empty_for_empty_string(self):
        urls = discover_pages("")
        assert urls == []

    def test_strips_path_from_base_url(self):
        urls = discover_pages("https://example.com/some/deep/path")
        # Homepage should be the root, not the deep path
        assert urls[0] == "https://example.com"

    def test_handles_url_with_trailing_slash(self):
        urls = discover_pages("https://example.com/")
        assert urls[0] == "https://example.com"
