"""Tests for SqliteFileTreeStore — file-tree persistence (spec 029, slice 1).

The store holds the set of tracked file paths per repository as a snapshot:
``save_file_paths`` replaces the previous set (delete-then-insert), not appends.
"""

from pathlib import Path

import pytest

from git_it.repository_ingestion.infrastructure.sqlite import SqliteFileTreeStore


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "file_tree_test.sqlite3"
    SqliteFileTreeStore(path).initialize()
    return path


def test_get_file_paths_returns_empty_when_absent(db_path: Path) -> None:
    assert SqliteFileTreeStore(db_path).get_file_paths("repo-1") == []


def test_save_and_get_file_paths_roundtrips(db_path: Path) -> None:
    store = SqliteFileTreeStore(db_path)
    store.save_file_paths("repo-1", ["README.md", "src/app.py", "tests/test_app.py"])
    assert set(store.get_file_paths("repo-1")) == {
        "README.md",
        "src/app.py",
        "tests/test_app.py",
    }


def test_save_replaces_previous_snapshot(db_path: Path) -> None:
    store = SqliteFileTreeStore(db_path)
    store.save_file_paths("repo-1", ["old/gone.py", "keep.py"])
    store.save_file_paths("repo-1", ["keep.py", "new/added.py"])
    assert set(store.get_file_paths("repo-1")) == {"keep.py", "new/added.py"}


def test_save_empty_set_clears_previous_snapshot(db_path: Path) -> None:
    store = SqliteFileTreeStore(db_path)
    store.save_file_paths("repo-1", ["a.py", "b.py"])
    store.save_file_paths("repo-1", [])
    assert store.get_file_paths("repo-1") == []


def test_different_repos_are_independent(db_path: Path) -> None:
    store = SqliteFileTreeStore(db_path)
    store.save_file_paths("repo-1", ["a.py"])
    store.save_file_paths("repo-2", ["b.py"])
    assert store.get_file_paths("repo-1") == ["a.py"]
    assert store.get_file_paths("repo-2") == ["b.py"]


def test_initialize_is_idempotent(db_path: Path) -> None:
    store = SqliteFileTreeStore(db_path)
    store.initialize()
    store.save_file_paths("repo-1", ["a.py"])
    assert store.get_file_paths("repo-1") == ["a.py"]
