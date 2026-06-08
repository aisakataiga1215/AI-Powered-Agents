"""Crawler service.

For the MVP, the CollectorAgent typically reads pre-canned fixture data
from ``scripts/demo_fixtures/`` to keep demos deterministic. Live
crawling is gated behind ``ENABLE_LIVE_SEARCH`` and is not implemented
in this scaffold.

The ``crawl_page`` / ``_is_allowed_by_robots`` additions below implement
the v1 live crawl path; they are only called when ``data_mode`` is
``"live_with_fallback"``.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from pydantic import ValidationError

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.source import SourceEvidence, SourceType

logger = get_logger(__name__)

# ``backend/app/services/crawler_service.py`` -> project root is three
# directories up.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEMO_FIXTURES_DIR = _PROJECT_ROOT / "scripts" / "demo_fixtures"

MAX_CONTENT_CHARS = 8_000
REQUEST_TIMEOUT = 10
USER_AGENT = "AgentInsight/1.0 (competitive analysis bot)"


@dataclass
class CrawledPage:
    url: str
    title: str
    snippet: str
    content: str
    status_code: int
    robots_status: str  # "allowed" | "disallowed" | "unchecked"


def _fixture_path(competitor_name: str) -> Path:
    slug = competitor_name.strip().lower().replace(" ", "_")
    return DEMO_FIXTURES_DIR / f"{slug}_sources.json"


def fixture_exists(competitor_name: str) -> bool:
    """Return True if a demo fixture file exists for this competitor.

    Side-effect-free — only checks file presence, does not read or parse.
    """
    if not settings.enable_demo_fixtures:
        return False
    return _fixture_path(competitor_name).exists()


def load_demo_fixtures(
    competitor_name: str,
    *,
    include_pricing: bool = True,
) -> list[SourceEvidence]:
    """Load demo fixture sources for a competitor.

    Args:
        competitor_name: Used to locate ``{slug}_sources.json``.
        include_pricing: When False, sources of type ``pricing_page`` are
            filtered out. The CollectorAgent uses this to exercise the
            QA rework loop in ``demo_scenario=missing_pricing_source``.

    Returns an empty list when:
    - ``ENABLE_DEMO_FIXTURES`` is false
    - the fixture file is missing
    - the fixture file is malformed
    """
    if not settings.enable_demo_fixtures:
        return []

    fixture_path = _fixture_path(competitor_name)
    if not fixture_path.exists():
        logger.warning(
            "Demo fixture not found for competitor '%s': %s",
            competitor_name,
            fixture_path,
        )
        return []

    try:
        raw = fixture_path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to read demo fixture %s: %s", fixture_path, exc)
        return []

    if not isinstance(payload, list):
        logger.error(
            "Demo fixture %s must contain a JSON array, got %s",
            fixture_path,
            type(payload).__name__,
        )
        return []

    sources: list[SourceEvidence] = []
    for item in payload:
        try:
            sources.append(SourceEvidence.model_validate(item))
        except ValidationError as exc:
            logger.warning(
                "Skipping invalid source in %s: %s", fixture_path, exc
            )

    if not include_pricing:
        kept = [s for s in sources if s.source_type is not SourceType.pricing_page]
        dropped = len(sources) - len(kept)
        if dropped:
            logger.info(
                "load_demo_fixtures: withheld %d pricing_page source(s) for '%s'",
                dropped,
                competitor_name,
            )
        sources = kept

    return sources


def is_live_search_enabled() -> bool:
    return bool(settings.enable_live_search)


def _is_allowed_by_robots(url: str) -> tuple[bool, str]:
    """Check robots.txt for the given URL.

    Returns (allowed, status_str). On any fetch or parse failure the
    caller is allowed to proceed and the status is "unchecked".
    """
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        resp = httpx.get(
            robots_url,
            timeout=5,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return True, "unchecked"
        rp = RobotFileParser()
        rp.parse(resp.text.splitlines())
        allowed = rp.can_fetch(USER_AGENT, url)
        return allowed, "allowed" if allowed else "disallowed"
    except Exception:  # noqa: BLE001
        return True, "unchecked"


def _extract_text(html: str) -> tuple[str, str]:
    """Return (title, body_text) extracted from HTML via BeautifulSoup."""
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    body = soup.get_text(separator=" ")
    body = re.sub(r"\s+", " ", body).strip()
    return title, body


_BAD_PAGE_PATTERNS: tuple[str, ...] = (
    "discord",
    "just a moment",        # Cloudflare JS challenge
    "captcha",
    "verify you are human",
    "access denied",
    "403 forbidden",
    "cloudflare",
)


def _is_bad_page(title: str, body_preview: str) -> bool:
    """Return True when title or body preview signals a blocked/redirected page.

    Only matches explicit bad patterns (Discord, Cloudflare, captcha, access-denied).
    Does NOT match generic patterns like "login" or "not found" to avoid blocking
    legitimate pages.
    """
    combined = (title + " " + body_preview).lower()
    return any(pattern in combined for pattern in _BAD_PAGE_PATTERNS)


def crawl_page(url: str) -> CrawledPage | None:
    """Fetch a page and return a CrawledPage, or None on failure.

    Returns None when:
    - robots.txt disallows the URL
    - HTTP status != 200
    - Content-Type is not text/html
    - Timeout or transport error after one retry
    """
    allowed, robots_status = _is_allowed_by_robots(url)
    if not allowed:
        logger.info("crawl_page: robots.txt disallows %s", url)
        return None

    headers = {"User-Agent": USER_AGENT}
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            resp = httpx.get(
                url,
                timeout=REQUEST_TIMEOUT,
                headers=headers,
                follow_redirects=True,
            )
            break
        except httpx.TransportError as exc:
            last_exc = exc
            if attempt == 0:
                logger.debug("crawl_page: transport error on %s, retrying", url)
            continue
    else:
        logger.warning("crawl_page: failed to fetch %s: %s", url, last_exc)
        return None

    if resp.status_code != 200:
        logger.debug("crawl_page: HTTP %d for %s", resp.status_code, url)
        return None

    content_type = resp.headers.get("content-type", "")
    if "text/html" not in content_type:
        logger.debug("crawl_page: non-HTML content-type '%s' for %s", content_type, url)
        return None

    title, body = _extract_text(resp.text)

    if _is_bad_page(title, body[:300]):
        logger.debug("crawl_page: bad page '%s' for %s", title, url)
        return None

    snippet = body[:300]
    content = body[:MAX_CONTENT_CHARS]

    return CrawledPage(
        url=url,
        title=title,
        snippet=snippet,
        content=content,
        status_code=resp.status_code,
        robots_status=robots_status,
    )
