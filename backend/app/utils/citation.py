"""Citation utilities.

Extracts ``source_id`` references from claim or report text. Used by
QA validation and citation rendering.
"""

import re

_SOURCE_ID_PATTERN = re.compile(r"\b(?:src_[a-f0-9]{6,}|source_[a-zA-Z0-9_]+)\b")


def extract_source_ids(text: str) -> list[str]:
    """Return a list of unique source IDs referenced in ``text``.

    Source IDs follow two conventions:
    - the generated ``src_<hex>`` pattern from :class:`SourceEvidence`
    - the legacy ``source_<token>`` style used in the schema examples
    """
    if not text:
        return []
    seen: list[str] = []
    for match in _SOURCE_ID_PATTERN.findall(text):
        if match not in seen:
            seen.append(match)
    return seen
