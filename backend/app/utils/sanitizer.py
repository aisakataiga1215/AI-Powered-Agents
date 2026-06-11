"""PII desensitization for user-supplied survey and interview text.

Replaces personally identifiable information with stable placeholders so the
collector can store evidence snippets without exposing private data. The
intent is to keep business signal (preferences, complaints, feature asks)
while masking identifying tokens (names, contact info, identifiers).

Public surface:

- ``sanitize_text(text)`` returns ``(masked_text, contains_pii)``.

The redactor is regex-driven and intentionally conservative: when a pattern
matches it marks the result as containing PII and replaces the span with a
labelled placeholder such as ``[REDACTED:email]``. Callers persist only the
masked output and the ``contains_pii`` flag, never the original input.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Email: standard local-part@domain with TLD.
_EMAIL_RE = re.compile(
    r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
)

# `mailto:` URIs should be redacted even though we generally keep URLs.
_MAILTO_RE = re.compile(r"mailto:[^\s>]+", re.IGNORECASE)

# Chinese mainland mobile numbers: 1 + [3-9] + 9 digits, with optional +86/0086.
_CN_MOBILE_RE = re.compile(r"(?:\+?86[-\s]?|0086[-\s]?)?1[3-9]\d{9}")

# International phones: optional +country, then 7-14 digits with separators.
# Anchored to digit boundaries so we don't mash version strings or IDs.
_INTL_PHONE_RE = re.compile(
    r"(?<![\w.])\+\d{1,3}[\s.-]?\(?\d{1,4}\)?[\s.-]?\d{2,4}[\s.-]?\d{2,4}(?:[\s.-]?\d{2,4})?(?![\w.])",
)

# Mainland China resident identity card: 17 digits + final digit or 'X'.
_CN_ID_RE = re.compile(r"(?<!\d)(?:\d{17}[\dXx])(?!\d)")

# Chinese surname (single char) + given name (1-2 chars) followed by an honorific.
_CN_NAME_RE = re.compile(
    r"[\u4e00-\u9fa5]{2,3}(?=(?:先生|女士|小姐|总监|经理|主管|总经理|总裁|老师|博士))",
)


@dataclass(frozen=True)
class _Pattern:
    label: str
    regex: re.Pattern[str]


_PATTERNS: tuple[_Pattern, ...] = (
    _Pattern("mailto", _MAILTO_RE),
    _Pattern("email", _EMAIL_RE),
    _Pattern("id", _CN_ID_RE),
    _Pattern("phone", _CN_MOBILE_RE),
    _Pattern("phone", _INTL_PHONE_RE),
    _Pattern("name", _CN_NAME_RE),
)


def sanitize_text(text: str | None) -> tuple[str, bool]:
    """Mask PII inside ``text``.

    Returns a tuple of ``(masked_text, contains_pii)``. Empty / ``None``
    inputs return ``("", False)``. Each pattern is applied in declaration
    order; if any pattern matches at least once we flip the flag and replace
    the span with ``[REDACTED:<label>]`` so downstream readers know what was
    removed without seeing the original value.
    """

    if not text:
        return "", False

    masked = text
    contains_pii = False
    for pattern in _PATTERNS:
        placeholder = f"[REDACTED:{pattern.label}]"
        masked, hit_count = pattern.regex.subn(placeholder, masked)
        if hit_count:
            contains_pii = True
    return masked, contains_pii
