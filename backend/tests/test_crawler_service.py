"""Tests for crawler_service: CrawledPage, crawl_page, _is_allowed_by_robots."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.crawler_service import (
    CrawledPage,
    MAX_CONTENT_CHARS,
    _extract_text,
    _is_allowed_by_robots,
    crawl_page,
)


class TestExtractText:
    def test_returns_title_and_body(self):
        html = "<html><head><title>My Page</title></head><body><p>Hello world</p></body></html>"
        title, body = _extract_text(html)
        assert title == "My Page"
        assert "Hello world" in body

    def test_removes_script_and_style(self):
        html = (
            "<html><body>"
            "<script>var x=1;</script>"
            "<style>.foo{color:red}</style>"
            "<p>Visible text</p>"
            "</body></html>"
        )
        _, body = _extract_text(html)
        assert "var x=1" not in body
        assert ".foo" not in body
        assert "Visible text" in body

    def test_empty_title_when_missing(self):
        html = "<html><body><p>text</p></body></html>"
        title, _ = _extract_text(html)
        assert title == ""


class TestIsAllowedByRobots:
    def test_returns_unchecked_on_fetch_failure(self):
        with patch("app.services.crawler_service.httpx.get") as mock_get:
            mock_get.side_effect = Exception("connection refused")
            allowed, status = _is_allowed_by_robots("https://example.com/page")
        assert allowed is True
        assert status == "unchecked"

    def test_returns_unchecked_on_non_200(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("app.services.crawler_service.httpx.get", return_value=mock_resp):
            allowed, status = _is_allowed_by_robots("https://example.com/page")
        assert allowed is True
        assert status == "unchecked"

    def test_allowed_when_robots_permits(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "User-agent: *\nAllow: /"
        with patch("app.services.crawler_service.httpx.get", return_value=mock_resp):
            allowed, status = _is_allowed_by_robots("https://example.com/page")
        assert allowed is True
        assert status == "allowed"

    def test_disallowed_when_robots_blocks(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "User-agent: *\nDisallow: /"
        with patch("app.services.crawler_service.httpx.get", return_value=mock_resp):
            allowed, status = _is_allowed_by_robots("https://example.com/page")
        assert allowed is False
        assert status == "disallowed"


class TestCrawlPage:
    def _make_html_response(self, html: str, status_code: int = 200, content_type: str = "text/html"):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.headers = {"content-type": content_type}
        mock_resp.text = html
        return mock_resp

    def test_returns_crawled_page_on_success(self):
        html = "<html><head><title>Pricing</title></head><body><p>$10/mo</p></body></html>"
        resp = self._make_html_response(html)
        with (
            patch("app.services.crawler_service._is_allowed_by_robots", return_value=(True, "allowed")),
            patch("app.services.crawler_service.httpx.get", return_value=resp),
        ):
            page = crawl_page("https://example.com/pricing")
        assert page is not None
        assert isinstance(page, CrawledPage)
        assert page.title == "Pricing"
        assert "$10/mo" in page.snippet
        assert page.status_code == 200
        assert page.robots_status == "allowed"

    def test_returns_none_on_non_200(self):
        resp = self._make_html_response("", status_code=404)
        with (
            patch("app.services.crawler_service._is_allowed_by_robots", return_value=(True, "allowed")),
            patch("app.services.crawler_service.httpx.get", return_value=resp),
        ):
            page = crawl_page("https://example.com/missing")
        assert page is None

    def test_returns_none_on_non_html_content_type(self):
        resp = self._make_html_response("{}", content_type="application/json")
        with (
            patch("app.services.crawler_service._is_allowed_by_robots", return_value=(True, "allowed")),
            patch("app.services.crawler_service.httpx.get", return_value=resp),
        ):
            page = crawl_page("https://example.com/api/data")
        assert page is None

    def test_returns_none_when_robots_disallows(self):
        with patch(
            "app.services.crawler_service._is_allowed_by_robots",
            return_value=(False, "disallowed"),
        ):
            page = crawl_page("https://example.com/private")
        assert page is None

    def test_content_truncated_to_max_chars(self):
        long_body = "x" * (MAX_CONTENT_CHARS + 1000)
        html = f"<html><head><title>T</title></head><body>{long_body}</body></html>"
        resp = self._make_html_response(html)
        with (
            patch("app.services.crawler_service._is_allowed_by_robots", return_value=(True, "allowed")),
            patch("app.services.crawler_service.httpx.get", return_value=resp),
        ):
            page = crawl_page("https://example.com/")
        assert page is not None
        assert len(page.content) <= MAX_CONTENT_CHARS

    def test_retries_on_transport_error_then_succeeds(self):
        import httpx as _httpx
        html = "<html><head><title>T</title></head><body>ok</body></html>"
        resp = self._make_html_response(html)
        side_effects = [_httpx.TransportError("timeout"), resp]
        with (
            patch("app.services.crawler_service._is_allowed_by_robots", return_value=(True, "allowed")),
            patch("app.services.crawler_service.httpx.get", side_effect=side_effects),
        ):
            page = crawl_page("https://example.com/")
        assert page is not None

    def test_returns_none_after_two_transport_errors(self):
        import httpx as _httpx
        with (
            patch("app.services.crawler_service._is_allowed_by_robots", return_value=(True, "allowed")),
            patch(
                "app.services.crawler_service.httpx.get",
                side_effect=[_httpx.TransportError("t1"), _httpx.TransportError("t2")],
            ),
        ):
            page = crawl_page("https://example.com/")
        assert page is None
