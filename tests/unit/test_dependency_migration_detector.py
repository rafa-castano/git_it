"""Tests for the dependency migration detector (Batch 46)."""

from git_it.repository_ingestion.application.pattern_detection_service import (
    _compute_dependency_migrations,
)
from git_it.repository_ingestion.application.ports import CommitSummaryRecord
from git_it.repository_ingestion.domain.patterns import DependencyMigration


def _summary(sha: str, message: str) -> CommitSummaryRecord:
    return CommitSummaryRecord(sha=sha, message=message)


def test_detects_migrate_from_x_to_y() -> None:
    summaries = [_summary("abc1234", "migrate from requests to httpx")]
    result = _compute_dependency_migrations(summaries, date_map={})
    assert len(result) == 1
    assert result[0].from_dependency == "requests"
    assert result[0].to_dependency == "httpx"


def test_detects_replace_x_with_y() -> None:
    summaries = [_summary("abc1234", "replace unittest with pytest")]
    result = _compute_dependency_migrations(summaries, date_map={})
    assert len(result) == 1
    assert result[0].from_dependency == "unittest"
    assert result[0].to_dependency == "pytest"


def test_detects_switch_from_x_to_y() -> None:
    summaries = [_summary("abc1234", "switch from flask to fastapi")]
    result = _compute_dependency_migrations(summaries, date_map={})
    assert len(result) == 1
    assert result[0].from_dependency == "flask"
    assert result[0].to_dependency == "fastapi"


def test_groups_same_migration_across_commits() -> None:
    summaries = [
        _summary("abc1234", "migrate from requests to httpx"),
        _summary("def5678", "migrate from requests to httpx in async layer"),
    ]
    result = _compute_dependency_migrations(summaries, date_map={})
    assert len(result) == 1
    assert result[0].commit_count == 2


def test_filters_short_token_noise() -> None:
    summaries = [_summary("abc1234", "move from a to b")]
    result = _compute_dependency_migrations(summaries, date_map={})
    assert result == []


def test_filters_common_word_noise() -> None:
    summaries = [_summary("abc1234", "migrate from the old to the new")]
    result = _compute_dependency_migrations(summaries, date_map={})
    assert result == []


def test_confidence_scales_with_commit_count() -> None:
    summaries_1 = [_summary("abc1234", "migrate from requests to httpx")]
    result_1 = _compute_dependency_migrations(summaries_1, date_map={})
    assert abs(result_1[0].confidence - round(1 / 3.0, 10)) < 1e-9

    summaries_3 = [
        _summary("abc1234", "migrate from requests to httpx"),
        _summary("def5678", "migrate from requests to httpx v2"),
        _summary("ghi9012", "migrate from requests to httpx done"),
    ]
    result_3 = _compute_dependency_migrations(summaries_3, date_map={})
    assert result_3[0].confidence == 1.0


def test_evidence_shas_populated() -> None:
    summaries = [
        _summary("abc1234", "migrate from requests to httpx"),
        _summary("def5678", "switch from requests to httpx"),
    ]
    result = _compute_dependency_migrations(summaries, date_map={})
    assert len(result) == 1
    assert "abc1234" in result[0].evidence_commit_shas
    assert "def5678" in result[0].evidence_commit_shas


def test_no_migration_keywords_returns_empty() -> None:
    summaries = [
        _summary("abc1234", "fix: handle null pointer in auth"),
        _summary("def5678", "chore: bump version to 2.0"),
        _summary("ghi9012", "docs: update README"),
    ]
    result = _compute_dependency_migrations(summaries, date_map={})
    assert result == []


def test_dependency_migration_dataclass_fields() -> None:
    m = DependencyMigration(
        from_dependency="requests",
        to_dependency="httpx",
        commit_count=2,
        evidence_commit_shas=("abc1234",),
        time_range=("2024-01-01", "2024-06-01"),
        confidence=0.67,
    )
    assert m.from_dependency == "requests"
    assert m.to_dependency == "httpx"
    assert m.commit_count == 2
