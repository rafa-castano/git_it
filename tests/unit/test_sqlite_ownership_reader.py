from pathlib import Path

import pytest

from git_it.repository_ingestion.domain.commits import ExtractedCommit, ExtractedFileChange
from git_it.repository_ingestion.infrastructure.sqlite import (
    SqliteCommitFactStore,
    SqliteFileFactReader,
    SqliteFileFactStore,
)


def _commit(
    sha: str,
    author: str,
    files: list[str],
    committed_at: str = "2024-01-01T00:00:00",
) -> ExtractedCommit:
    return ExtractedCommit(
        sha=sha,
        committed_at=committed_at,
        message="msg",
        author_name=author,
        committer_name=author,
        parent_shas=(),
        file_changes=tuple(ExtractedFileChange(path=f, insertions=1, deletions=0) for f in files),
    )


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.sqlite3"
    SqliteCommitFactStore(path).initialize()
    SqliteFileFactStore(path).initialize()
    return path


def test_get_file_ownership_returns_empty_when_no_data(db_path: Path) -> None:
    result = SqliteFileFactReader(db_path).get_file_ownership("repo-1")
    assert result == []


def test_get_file_ownership_counts_distinct_authors(db_path: Path) -> None:
    commits = [
        _commit("s1", "alice", ["src/auth.py"]),
        _commit("s2", "bob", ["src/auth.py"]),
    ]
    SqliteCommitFactStore(db_path).save_commit_facts(commits, repository_id="repo-1")
    SqliteFileFactStore(db_path).save_file_facts(commits, repository_id="repo-1")

    records = SqliteFileFactReader(db_path).get_file_ownership("repo-1")
    auth = next(r for r in records if r.file_path == "src/auth.py")
    assert auth.author_count == 2


def test_get_file_ownership_singleton_author(db_path: Path) -> None:
    commits = [
        _commit("s1", "alice", ["src/utils.py"]),
        _commit("s2", "alice", ["src/utils.py"]),
    ]
    SqliteCommitFactStore(db_path).save_commit_facts(commits, repository_id="repo-1")
    SqliteFileFactStore(db_path).save_file_facts(commits, repository_id="repo-1")

    records = SqliteFileFactReader(db_path).get_file_ownership("repo-1")
    utils = next(r for r in records if r.file_path == "src/utils.py")
    assert utils.author_count == 1
    assert utils.commit_count == 2


def test_get_file_ownership_isolates_by_repository(db_path: Path) -> None:
    commits = [_commit("s1", "alice", ["src/main.py"])]
    SqliteCommitFactStore(db_path).save_commit_facts(commits, repository_id="repo-1")
    SqliteFileFactStore(db_path).save_file_facts(commits, repository_id="repo-1")

    assert SqliteFileFactReader(db_path).get_file_ownership("repo-2") == []
