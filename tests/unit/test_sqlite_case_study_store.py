from pathlib import Path

import pytest

from git_it.repository_ingestion.application.ports import CaseStudyRecord
from git_it.repository_ingestion.infrastructure.sqlite import SqliteCaseStudyStore


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.sqlite3"
    SqliteCaseStudyStore(path).initialize()
    return path


def test_get_case_study_returns_none_when_empty(db_path: Path) -> None:
    assert SqliteCaseStudyStore(db_path).get_case_study("repo-1") is None


def test_save_and_get_case_study(db_path: Path) -> None:
    record = CaseStudyRecord(
        repository_id="repo-1",
        narrative="# Case Study\nContent here.",
        commit_count=10,
        hotspot_count=3,
    )
    store = SqliteCaseStudyStore(db_path)
    store.save_case_study(record)
    result = store.get_case_study("repo-1")
    assert result is not None
    assert result.repository_id == "repo-1"
    assert result.narrative == "# Case Study\nContent here."
    assert result.commit_count == 10
    assert result.hotspot_count == 3


def test_save_overwrites_existing(db_path: Path) -> None:
    store = SqliteCaseStudyStore(db_path)
    store.save_case_study(
        CaseStudyRecord(repository_id="repo-1", narrative="old", commit_count=5, hotspot_count=1)
    )
    store.save_case_study(
        CaseStudyRecord(repository_id="repo-1", narrative="new", commit_count=7, hotspot_count=2)
    )
    result = store.get_case_study("repo-1")
    assert result is not None
    assert result.narrative == "new"
    assert result.commit_count == 7


def test_get_case_study_isolated_by_repository(db_path: Path) -> None:
    store = SqliteCaseStudyStore(db_path)
    store.save_case_study(
        CaseStudyRecord(
            repository_id="repo-1", narrative="repo1 study", commit_count=5, hotspot_count=0
        )
    )
    assert store.get_case_study("repo-2") is None


def test_get_repo_context_returns_none_when_no_case_study(db_path: Path) -> None:
    assert SqliteCaseStudyStore(db_path).get_repo_context("repo-1") is None


def test_get_repo_context_truncates_long_narrative(db_path: Path) -> None:
    long_narrative = "x" * 5000
    store = SqliteCaseStudyStore(db_path)
    store.save_case_study(
        CaseStudyRecord(
            repository_id="repo-1",
            narrative=long_narrative,
            commit_count=1,
            hotspot_count=0,
        )
    )
    result = store.get_repo_context("repo-1")
    assert result is not None
    assert len(result) <= 2000


# ---------------------------------------------------------------------------
# Audience-specific caching (Batch 67)
# ---------------------------------------------------------------------------


def test_save_and_get_audience_specific_record(db_path: Path) -> None:
    store = SqliteCaseStudyStore(db_path)
    store.save_case_study(
        CaseStudyRecord(
            repository_id="repo-1",
            narrative="beginner narrative",
            commit_count=5,
            hotspot_count=1,
            audience="beginner",
        )
    )
    result = store.get_case_study("repo-1", audience="beginner")
    assert result is not None
    assert result.narrative == "beginner narrative"
    assert result.audience == "beginner"


def test_audience_miss_returns_none(db_path: Path) -> None:
    store = SqliteCaseStudyStore(db_path)
    store.save_case_study(
        CaseStudyRecord(
            repository_id="repo-1",
            narrative="only beginner",
            commit_count=5,
            hotspot_count=0,
            audience="beginner",
        )
    )
    assert store.get_case_study("repo-1", audience="expert") is None


def test_different_audiences_stored_independently(db_path: Path) -> None:
    store = SqliteCaseStudyStore(db_path)
    store.save_case_study(
        CaseStudyRecord(
            repository_id="repo-1",
            narrative="expert text",
            commit_count=10,
            hotspot_count=0,
            audience="expert",
        )
    )
    store.save_case_study(
        CaseStudyRecord(
            repository_id="repo-1",
            narrative="beginner text",
            commit_count=10,
            hotspot_count=0,
            audience="beginner",
        )
    )
    assert store.get_case_study("repo-1", "expert").narrative == "expert text"  # type: ignore[union-attr]
    assert store.get_case_study("repo-1", "beginner").narrative == "beginner text"  # type: ignore[union-attr]


def test_save_overwrites_same_audience_only(db_path: Path) -> None:
    store = SqliteCaseStudyStore(db_path)
    store.save_case_study(
        CaseStudyRecord(
            repository_id="repo-1",
            narrative="v1",
            commit_count=5,
            hotspot_count=0,
            audience="beginner",
        )
    )
    store.save_case_study(
        CaseStudyRecord(
            repository_id="repo-1",
            narrative="v2",
            commit_count=8,
            hotspot_count=1,
            audience="beginner",
        )
    )
    result = store.get_case_study("repo-1", "beginner")
    assert result is not None
    assert result.narrative == "v2"


def test_migration_from_single_pk_schema(tmp_path: Path) -> None:
    import sqlite3

    db_path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE case_studies (
                repository_id TEXT PRIMARY KEY,
                narrative     TEXT NOT NULL,
                commit_count  INTEGER NOT NULL,
                hotspot_count INTEGER NOT NULL,
                created_at    TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            "INSERT INTO case_studies (repository_id, narrative, commit_count, hotspot_count)"
            " VALUES ('repo-legacy', 'old narrative', 7, 2)"
        )

    store = SqliteCaseStudyStore(db_path)
    store.initialize()

    result = store.get_case_study("repo-legacy", audience="beginner")
    assert result is not None
    assert result.narrative == "old narrative"
    assert result.audience == "beginner"
