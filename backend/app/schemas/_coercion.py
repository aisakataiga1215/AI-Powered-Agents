"""LLM-output coercion helpers.

OpenAI-compatible structured output sometimes returns a single string
where the schema declares ``list[str]`` (e.g. DeepSeek emitting a
narrative paragraph for ``pain_points``). Strict Pydantic validation
then aborts the whole tool call. Wrapping the affected fields with
:data:`StrList` accepts both shapes without distorting the data.
"""

from typing import Annotated, Any

from pydantic import BeforeValidator


def _to_str_list(value: Any) -> list[str]:
    """Coerce ``None`` or a single string into a ``list[str]``.

    Existing lists pass through unchanged (after element stringification)
    so genuine multi-item arrays are preserved. A lone string becomes a
    one-element list — we deliberately do NOT split on commas/newlines
    because the LLM's intended boundary is ambiguous and splitting risks
    fabricating distinct items from a single sentence.
    """
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if item is not None]
    return [str(value)]


StrList = Annotated[list[str], BeforeValidator(_to_str_list)]
