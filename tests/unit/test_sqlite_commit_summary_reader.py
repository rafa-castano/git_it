from pathlib import Path

import pytest

from git_it.repository_ingestion.domain.commits import ExtractedCommit
from git_it.repository_ingestion.infrastructure.sqlite import (
    SqliteCommitFactStore,
    SqliteCommitReader,
)


def _commit(sha: str, message: str, committed_at: str = "2024-01-01T00:00:00") -> ExtractedCommit:
    return ExtractedCommit(
        sha=sha,
        committed_at=committed_at,
        message=message,
        author_name="author",
        committer_name="author",
        parent_shas=(),
        file_changes=(),
    )


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.sqlite3"
    SqliteCommitFactStore(path).initialize()
    return path


def test_list_commit_messages_empty_when_no_data(db_path: Path) -> None:
    result = SqliteCommitReader(db_path).list_commit_messages("repo-1")
    assert result == []


def test_list_commit_messages_returns_records(db_path: Path) -> None:
    SqliteCommitFactStore(db_path).save_commit_facts(
        [_commit("abc123", "feat: add login")], repository_id="repo-1"
    )
    records = SqliteCommitReader(db_path).list_commit_messages("repo-1")
    assert len(records) == 1
    assert records[0].sha == "abc123"
    assert records[0].message == "feat: add login"


def test_list_commit_messages_returns_all_messages(db_path: Path) -> None:
    commits = [
        _commit("s1", "feat: one"),
        _commit("s2", 'Revert "feat: one"'),
        _commit("s3", "fix: bug"),
    ]
    SqliteCommitFactStore(db_path).save_commit_facts(commits, repository_id="repo-1")
    records = SqliteCommitReader(db_path).list_commit_messages("repo-1")
    assert len(records) == 3


def test_list_commit_messages_isolated_by_repository(db_path: Path) -> None:
    SqliteCommitFactStore(db_path).save_commit_facts(
        [_commit("s1", "feat: repo1 commit")], repository_id="repo-1"
    )
    result = SqliteCommitReader(db_path).list_commit_messages("repo-2")
    assert result == []
