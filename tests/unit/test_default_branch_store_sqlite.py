"""Tests for SqliteDefaultBranchStore — default branch persistence (spec 020)."""

from pathlib import Path

import pytest

from git_it.repository_ingestion.infrastructure.sqlite import SqliteDefaultBranchStore


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "default_branch_test.sqlite3"
    SqliteDefaultBranchStore(path).initialize()
    return path


def test_get_default_branch_returns_none_when_absent(db_path: Path) -> None:
    assert SqliteDefaultBranchStore(db_path).get_default_branch("repo-1") is None


def test_save_and_get_default_branch_roundtrips(db_path: Path) -> None:
    store = SqliteDefaultBranchStore(db_path)
    store.save_default_branch("repo-1", "main")
    assert store.get_default_branch("repo-1") == "main"


def test_save_overwrites_existing_default_branch(db_path: Path) -> None:
    store = SqliteDefaultBranchStore(db_path)
    store.save_default_branch("repo-1", "main")
    store.save_default_branch("repo-1", "develop")
    assert store.get_default_branch("repo-1") == "develop"


def test_different_repos_are_independent(db_path: Path) -> None:
    store = SqliteDefaultBranchStore(db_path)
    store.save_default_branch("repo-1", "main")
    store.save_default_branch("repo-2", "master")
    assert store.get_default_branch("repo-1") == "main"
    assert store.get_default_branch("repo-2") == "master"


def test_initialize_is_idempotent(db_path: Path) -> None:
    store = SqliteDefaultBranchStore(db_path)
    store.initialize()
    store.save_default_branch("repo-1", "main")
    assert store.get_default_branch("repo-1") == "main"
