"""AC-1: SqliteCaseStudyStore.list_available_audiences — spec 010."""

import sqlite3
from pathlib import Path

from git_it.repository_ingestion.infrastructure.sqlite import SqliteCaseStudyStore


def _make_store(tmp_path: Path) -> SqliteCaseStudyStore:
    db = tmp_path / "git-it.sqlite3"
    store = SqliteCaseStudyStore(db)
    store.initialize()
    return store


def _seed_case_study(db: Path, repository_id: str, audience: str) -> None:
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO case_studies
              (repository_id, narrative, commit_count, hotspot_count, audience)
            VALUES (?, ?, ?, ?, ?)
            """,
            (repository_id, "## Overview\nTest narrative.", 10, 2, audience),
        )


def test_list_available_audiences_returns_empty_when_no_rows(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    result = store.list_available_audiences("repo-missing")
    assert result == []


def test_list_available_audiences_single_audience(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    _seed_case_study(tmp_path / "git-it.sqlite3", "repo-1", "beginner")
    result = store.list_available_audiences("repo-1")
    assert result == ["beginner"]


def test_list_available_audiences_two_audiences_sorted(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    db = tmp_path / "git-it.sqlite3"
    _seed_case_study(db, "repo-1", "expert")
    _seed_case_study(db, "repo-1", "beginner")
    result = store.list_available_audiences("repo-1")
    assert result == ["beginner", "expert"]


def test_list_available_audiences_scoped_to_repository(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    db = tmp_path / "git-it.sqlite3"
    _seed_case_study(db, "repo-A", "beginner")
    _seed_case_study(db, "repo-B", "expert")
    assert store.list_available_audiences("repo-A") == ["beginner"]
    assert store.list_available_audiences("repo-B") == ["expert"]
