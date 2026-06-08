"""Citation utility tests."""

from app.utils.citation import extract_source_ids


def test_extract_source_ids_finds_both_styles():
    text = (
        "Cursor offers AI completions [src_abc12345] and "
        "uses a freemium pricing model [source_pricing_001]."
    )
    ids = extract_source_ids(text)
    assert "src_abc12345" in ids
    assert "source_pricing_001" in ids


def test_extract_source_ids_deduplicates():
    text = "see src_abc12345 and src_abc12345 again"
    ids = extract_source_ids(text)
    assert ids == ["src_abc12345"]


def test_extract_source_ids_empty_text():
    assert extract_source_ids("") == []
    assert extract_source_ids(None) == []  # type: ignore[arg-type]


def test_extract_source_ids_no_matches():
    assert extract_source_ids("nothing to see here") == []
