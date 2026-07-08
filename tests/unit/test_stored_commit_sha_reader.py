from pathlib import Path

import pytest

from git_it.repository_ingestion.domain.commits import ExtractedCommit
from git_it.repository_ingestion.infrastructure.sqlite import (
    SqliteCommitFactStore,
    SqliteStoredCommitShaReader,
)


def _make_commit(sha: str) -> ExtractedCommit:
    return ExtractedCommit(
        sha=sha,
        committed_at="2026-01-01T00:00:00+00:00",
        message="msg",
        author_name="Author",
        committer_name="Committer",
        parent_shas=(),
    )


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "git-it.db"
    store = SqliteCommitFactStore(path)
    store.initialize()
    return path


def test_sqlite_stored_commit_sha_reader_returns_stored_shas_as_a_set(db_path: Path) -> None:
    SqliteCommitFactStore(db_path).save_commit_facts(
        [_make_commit("aaa"), _make_commit("bbb")], repository_id="repo-1"
    )

    reader = SqliteStoredCommitShaReader(db_path)

    assert reader.read_stored_shas("repo-1") == {"aaa", "bbb"}


def test_sqlite_stored_commit_sha_reader_returns_empty_set_for_unknown_repo(db_path: Path) -> None:
    reader = SqliteStoredCommitShaReader(db_path)

    assert reader.read_stored_shas("repo-does-not-exist") == set()


def test_sqlite_stored_commit_sha_reader_scopes_shas_to_the_requested_repository(
    db_path: Path,
) -> None:
    SqliteCommitFactStore(db_path).save_commit_facts([_make_commit("aaa")], repository_id="repo-1")
    SqliteCommitFactStore(db_path).save_commit_facts([_make_commit("bbb")], repository_id="repo-2")

    reader = SqliteStoredCommitShaReader(db_path)

    assert reader.read_stored_shas("repo-1") == {"aaa"}
    assert reader.read_stored_shas("repo-2") == {"bbb"}
