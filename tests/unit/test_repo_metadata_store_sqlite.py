"""Tests for SqliteRepoMetadataStore — stars + language breakdown persistence."""

from pathlib import Path

import pytest

from git_it.repository_ingestion.domain.repo_metadata import LanguageBreakdown, RepoMetadata
from git_it.repository_ingestion.infrastructure.sqlite import SqliteRepoMetadataStore


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "repo_metadata_test.sqlite3"
    SqliteRepoMetadataStore(path).initialize()
    return path


def test_get_repo_metadata_returns_none_when_absent(db_path: Path) -> None:
    assert SqliteRepoMetadataStore(db_path).get_repo_metadata("repo-1") is None


def test_save_and_get_repo_metadata_roundtrips(db_path: Path) -> None:
    store = SqliteRepoMetadataStore(db_path)
    metadata = RepoMetadata(
        stars=1234,
        languages=(
            LanguageBreakdown(language="Python", bytes=300),
            LanguageBreakdown(language="HTML", bytes=100),
        ),
    )
    store.save_repo_metadata("repo-1", metadata)
    result = store.get_repo_metadata("repo-1")
    assert result == metadata


def test_save_repo_metadata_with_empty_languages(db_path: Path) -> None:
    store = SqliteRepoMetadataStore(db_path)
    store.save_repo_metadata("repo-1", RepoMetadata(stars=7, languages=()))
    result = store.get_repo_metadata("repo-1")
    assert result == RepoMetadata(stars=7, languages=())


def test_save_overwrites_existing_metadata(db_path: Path) -> None:
    store = SqliteRepoMetadataStore(db_path)
    store.save_repo_metadata("repo-1", RepoMetadata(stars=1, languages=()))
    store.save_repo_metadata(
        "repo-1", RepoMetadata(stars=99, languages=(LanguageBreakdown(language="Go", bytes=50),))
    )
    result = store.get_repo_metadata("repo-1")
    assert result == RepoMetadata(stars=99, languages=(LanguageBreakdown(language="Go", bytes=50),))


def test_different_repos_are_independent(db_path: Path) -> None:
    store = SqliteRepoMetadataStore(db_path)
    store.save_repo_metadata("repo-1", RepoMetadata(stars=1, languages=()))
    store.save_repo_metadata("repo-2", RepoMetadata(stars=2, languages=()))
    assert store.get_repo_metadata("repo-1") == RepoMetadata(stars=1, languages=())
    assert store.get_repo_metadata("repo-2") == RepoMetadata(stars=2, languages=())


def test_initialize_is_idempotent(db_path: Path) -> None:
    store = SqliteRepoMetadataStore(db_path)
    store.initialize()
    store.save_repo_metadata("repo-1", RepoMetadata(stars=1, languages=()))
    assert store.get_repo_metadata("repo-1") == RepoMetadata(stars=1, languages=())
