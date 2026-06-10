"""Competitor schema.

A competitor represents a product or company being analyzed in a
project. The :class:`CompetitorInput` form is used to accept user input
when creating a project.
"""

import uuid
import ipaddress
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

CompetitorRole = Literal[
    "direct_competitor",
    "indirect_competitor",
    "inspiration_product",
    "benchmark_leader",
]


MAX_EXTRA_URLS = 8
MAX_EXTRA_URL_LENGTH = 2048
_ALLOWED_EXTRA_URL_SCHEMES = {"http", "https"}
_BLOCKED_EXTRA_URL_HOSTS = {"localhost", "metadata.google.internal"}


def _is_blocked_extra_url_host(hostname: str) -> bool:
    host = hostname.strip().lower().removeprefix("www.")
    if not host or host in _BLOCKED_EXTRA_URL_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any((
        ip.is_private,
        ip.is_loopback,
        ip.is_link_local,
        ip.is_multicast,
        ip.is_reserved,
        ip.is_unspecified,
    ))


def normalize_public_url(value: str) -> str:
    url = (value or "").strip()
    if not url:
        raise ValueError("url is required")
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_EXTRA_URL_SCHEMES:
        raise ValueError("url must use http or https")
    if _is_blocked_extra_url_host(parsed.hostname or ""):
        raise ValueError("url must not target local or private hosts")
    return url


class CompetitorInput(BaseModel):
    name: str
    url: str
    role: CompetitorRole = "direct_competitor"
    extra_urls: list[str] = Field(default_factory=list, max_length=MAX_EXTRA_URLS)

    @field_validator("name")
    @classmethod
    def validate_name(cls, name: str) -> str:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("name is required")
        return cleaned

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, url: str) -> str:
        return normalize_public_url(str(url))

    @field_validator("extra_urls")
    @classmethod
    def validate_extra_urls(cls, urls: list[str]) -> list[str]:
        normalized_urls: list[str] = []
        for url in urls:
            if len(url) > MAX_EXTRA_URL_LENGTH:
                raise ValueError("extra_urls item is too long")
            normalized_urls.append(normalize_public_url(url))
        return normalized_urls


class Competitor(BaseModel):
    competitor_id: str = Field(default_factory=lambda: f"comp_{uuid.uuid4().hex[:8]}")
    name: str
    website: str
    description: str = ""
    metadata: dict = Field(default_factory=dict)
