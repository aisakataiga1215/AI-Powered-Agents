"""Text sanitizer.

Placeholder hook for stripping sensitive content from manually entered
user interviews or surveys. The MVP returns the input unchanged.
"""


def sanitize_text(text: str) -> str:
    """Return a sanitized copy of ``text``.

    MVP behavior is a passthrough so callers can wire in this function
    today and we can tighten the rules later without changing call sites.
    """
    if text is None:
        return ""
    return text
