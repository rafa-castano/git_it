"""Tests for map_languages — bytes-to-percent mapping (spec 019)."""

from git_it.api.mappers import map_languages
from git_it.api.schemas import LanguageItem
from git_it.repository_ingestion.domain.repo_metadata import LanguageBreakdown


def test_map_languages_empty_returns_empty_list() -> None:
    assert map_languages(()) == []


def test_map_languages_computes_percent() -> None:
    languages = (
        LanguageBreakdown(language="Python", bytes=300),
        LanguageBreakdown(language="HTML", bytes=100),
    )
    result = map_languages(languages)
    assert result == [
        LanguageItem(language="Python", bytes=300, percent=75.0),
        LanguageItem(language="HTML", bytes=100, percent=25.0),
    ]


def test_map_languages_preserves_order() -> None:
    languages = (
        LanguageBreakdown(language="Z", bytes=1),
        LanguageBreakdown(language="A", bytes=1),
    )
    result = map_languages(languages)
    assert [item.language for item in result] == ["Z", "A"]


def test_map_languages_rounds_to_one_decimal() -> None:
    languages = (
        LanguageBreakdown(language="A", bytes=1),
        LanguageBreakdown(language="B", bytes=2),
        LanguageBreakdown(language="C", bytes=3),
    )
    result = map_languages(languages)
    # 1/6=16.666..., 2/6=33.333..., 3/6=50.0
    assert [item.percent for item in result] == [16.7, 33.3, 50.0]
