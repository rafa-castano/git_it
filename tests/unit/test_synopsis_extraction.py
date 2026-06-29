from git_it.repository_ingestion.application.narrative_service import _extract_synopsis


def test_extract_no_synopsis_section() -> None:
    narrative = "## Overview\nSome content.\n\n## Timeline\nMore content."
    text, synopsis = _extract_synopsis(narrative)
    assert text == narrative
    assert synopsis is None


def test_extract_strips_synopsis_cleanly() -> None:
    narrative_part = "## Overview\nSome content.\n\n## Timeline\nMore content."
    synopsis_text = "Key patterns: hexagonal arch, TDD adoption, CI maturity."
    raw = narrative_part + "\n\n## Synopsis\n" + synopsis_text
    text, synopsis = _extract_synopsis(raw)
    assert text == narrative_part
    assert synopsis == synopsis_text


def test_extract_empty_synopsis_returns_none() -> None:
    raw = "## Overview\nContent.\n\n## Synopsis\n   \n"
    text, synopsis = _extract_synopsis(raw)
    assert text == raw
    assert synopsis is None


def test_extract_uses_last_synopsis_marker() -> None:
    raw = "## Overview\n## Synopsis\nignored\n\n## Synopsis\nreal synopsis"
    text, synopsis = _extract_synopsis(raw)
    assert synopsis == "real synopsis"
    assert "## Synopsis\nreal synopsis" not in text
