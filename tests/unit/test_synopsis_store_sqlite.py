"""Tests for SqliteSynopsisStore — audience-neutral synopsis persistence."""

from pathlib import Path

import pytest

from git_it.repository_ingestion.infrastructure.sqlite import SqliteSynopsisStore


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "synopsis_test.sqlite3"
    SqliteSynopsisStore(path).initialize()
    return path


def test_get_synopsis_returns_none_when_empty(db_path: Path) -> None:
    assert SqliteSynopsisStore(db_path).get_synopsis("repo-1") is None


def test_save_and_get_synopsis(db_path: Path) -> None:
    store = SqliteSynopsisStore(db_path)
    store.save_synopsis("repo-1", "Key patterns: TDD, hexagonal arch.")
    result = store.get_synopsis("repo-1")
    assert result == "Key patterns: TDD, hexagonal arch."


def test_save_overwrites_existing_synopsis(db_path: Path) -> None:
    store = SqliteSynopsisStore(db_path)
    store.save_synopsis("repo-1", "Old synopsis.")
    store.save_synopsis("repo-1", "New synopsis.")
    assert store.get_synopsis("repo-1") == "New synopsis."


def test_different_repos_are_independent(db_path: Path) -> None:
    store = SqliteSynopsisStore(db_path)
    store.save_synopsis("repo-1", "Synopsis A.")
    store.save_synopsis("repo-2", "Synopsis B.")
    assert store.get_synopsis("repo-1") == "Synopsis A."
    assert store.get_synopsis("repo-2") == "Synopsis B."


def test_initialize_is_idempotent(db_path: Path) -> None:
    store = SqliteSynopsisStore(db_path)
    store.initialize()
    store.initialize()
    store.save_synopsis("repo-1", "ok")
    assert store.get_synopsis("repo-1") == "ok"
