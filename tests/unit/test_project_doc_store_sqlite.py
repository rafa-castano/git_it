"""Tests for SqliteProjectDocStore — README/CHANGELOG persistence (spec 025)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from git_it.repository_ingestion.domain.project_docs import ProjectDocContent
from git_it.repository_ingestion.infrastructure.sqlite import SqliteProjectDocStore


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "project_docs_test.sqlite3"
    SqliteProjectDocStore(path).initialize()
    return path


def test_get_project_docs_returns_none_when_absent(db_path: Path) -> None:
    assert SqliteProjectDocStore(db_path).get_project_docs("repo-1") is None


def test_save_and_get_project_docs_roundtrips(db_path: Path) -> None:
    store = SqliteProjectDocStore(db_path)
    captured_at = datetime(2026, 1, 1, tzinfo=UTC)
    content = ProjectDocContent(
        repository_id="repo-1",
        readme_text="# Hello",
        readme_truncated=False,
        changelog_text="## v1.0.0",
        changelog_truncated=True,
        captured_at=captured_at,
    )
    store.save_project_docs(content)
    assert store.get_project_docs("repo-1") == content


def test_save_overwrites_existing_project_docs(db_path: Path) -> None:
    store = SqliteProjectDocStore(db_path)
    first = ProjectDocContent(
        repository_id="repo-1",
        readme_text="first",
        readme_truncated=False,
        changelog_text=None,
        changelog_truncated=False,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    second = ProjectDocContent(
        repository_id="repo-1",
        readme_text="second",
        readme_truncated=True,
        changelog_text="changed",
        changelog_truncated=False,
        captured_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    store.save_project_docs(first)
    store.save_project_docs(second)
    assert store.get_project_docs("repo-1") == second


def test_different_repositories_are_independent(db_path: Path) -> None:
    store = SqliteProjectDocStore(db_path)
    repo_1 = ProjectDocContent(
        repository_id="repo-1",
        readme_text="repo-1 readme",
        readme_truncated=False,
        changelog_text=None,
        changelog_truncated=False,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    repo_2 = ProjectDocContent(
        repository_id="repo-2",
        readme_text="repo-2 readme",
        readme_truncated=False,
        changelog_text=None,
        changelog_truncated=False,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    store.save_project_docs(repo_1)
    store.save_project_docs(repo_2)
    assert store.get_project_docs("repo-1") == repo_1
    assert store.get_project_docs("repo-2") == repo_2


def test_initialize_is_idempotent(db_path: Path) -> None:
    store = SqliteProjectDocStore(db_path)
    store.initialize()
    content = ProjectDocContent(
        repository_id="repo-1",
        readme_text="hello",
        readme_truncated=False,
        changelog_text=None,
        changelog_truncated=False,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    store.save_project_docs(content)
    assert store.get_project_docs("repo-1") == content


def test_readme_only_roundtrips_with_changelog_none(db_path: Path) -> None:
    store = SqliteProjectDocStore(db_path)
    content = ProjectDocContent(
        repository_id="repo-1",
        readme_text="only a readme",
        readme_truncated=False,
        changelog_text=None,
        changelog_truncated=False,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    store.save_project_docs(content)
    result = store.get_project_docs("repo-1")
    assert result is not None
    assert result.changelog_text is None
    assert result == content


def test_truncation_flags_roundtrip_as_real_booleans(db_path: Path) -> None:
    store = SqliteProjectDocStore(db_path)
    content = ProjectDocContent(
        repository_id="repo-1",
        readme_text="x" * 10,
        readme_truncated=True,
        changelog_text="y" * 10,
        changelog_truncated=False,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    store.save_project_docs(content)
    result = store.get_project_docs("repo-1")
    assert result is not None
    assert result.readme_truncated is True
    assert result.changelog_truncated is False
