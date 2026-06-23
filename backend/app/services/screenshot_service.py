"""Screenshot evidence capture for public source pages.

The collector treats screenshots as optional evidence. A failure to capture
must not fail a project run; text evidence remains the source of truth.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_ARTIFACT_ROOT = (_PROJECT_ROOT / settings.artifact_dir).resolve()
_BLOCKED_HOSTS = {"localhost", "metadata.google.internal"}


@dataclass(frozen=True)
class ScreenshotResult:
    path: str
    url: str


def artifact_root() -> Path:
    _ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    return _ARTIFACT_ROOT


def _is_public_http_url(raw_url: str) -> bool:
    try:
        parsed = urlparse(raw_url.strip())
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").strip().lower().removeprefix("www.")
    if not host or host in _BLOCKED_HOSTS or host.endswith(".local"):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not any(
        (
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        )
    )


def _filename_for_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    host = re.sub(r"[^\w.\-]+", "_", parsed.netloc or "page")[:80]
    digest = hashlib.sha256(raw_url.encode("utf-8")).hexdigest()[:12]
    return f"{host}_{digest}.png"


def capture_source_screenshot(
    *,
    project_id: str,
    source_id: str,
    url: str,
    full_page: bool = False,
) -> ScreenshotResult | None:
    if not settings.enable_screenshot_evidence:
        return None
    if not _is_public_http_url(url):
        return None

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.info("Screenshot evidence skipped: Playwright is not installed.")
        return None

    project_dir = artifact_root() / "screenshots" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    path = project_dir / f"{source_id}_{_filename_for_url(url)}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent="AgentInsight/1.0 screenshot evidence",
                    locale="zh-CN",
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                page.wait_for_timeout(800)
                page.screenshot(path=str(path), full_page=full_page)
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001
        logger.info("Screenshot evidence failed for %s: %s", url, exc)
        return None

    relative = path.relative_to(artifact_root()).as_posix()
    return ScreenshotResult(
        path=str(path),
        url=f"/artifacts/{relative}",
    )
