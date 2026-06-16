import json
import sqlite3
from pathlib import Path

import pytest

from git_it.repository_ingestion.application.commit_query_service import CommitRecord
from git_it.repository_ingestion.infrastructure.sqlite import SqliteCommitReader


def _seed_commit(
    connection: sqlite3.Connection,
    *,
    repository_id: str,
    sha: str,
    committed_at: str,
    message: str = "commit",
    author_name: str = "Author",
    parent_shas: list[str] | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO commit_facts (
            repository_id, sha, committed_at, message,
            author_name, committer_name, parent_shas
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            repository_id,
            sha,
            committed_at,
            message,
            author_name,
            author_name,
            json.dumps(parent_shas or []),
        ),
    )


@pytest.fixture()
def reader(tmp_path: Path) -> SqliteCommitReader:
    from git_it.repository_ingestion.infrastructure.sqlite import SqliteCommitFactStore

    store = SqliteCommitFactStore(tmp_path / "git-it.db")
    store.initialize()
    return SqliteCommitReader(tmp_path / "git-it.db")


@pytest.fixture()
def seeded_reader(tmp_path: Path) -> SqliteCommitReader:
    from git_it.repository_ingestion.infrastructure.sqlite import SqliteCommitFactStore

    db_path = tmp_path / "git-it.db"
    store = SqliteCommitFactStore(db_path)
    store.initialize()

    with sqlite3.connect(db_path) as conn:
        _seed_commit(conn, repository_id="repo-1", sha="aaa", committed_at="2026-01-03")
        _seed_commit(conn, repository_id="repo-1", sha="bbb", committed_at="2026-01-02")
        _seed_commit(conn, repository_id="repo-1", sha="ccc", committed_at="2026-01-01")
        _seed_commit(conn, repository_id="repo-2", sha="xxx", committed_at="2026-01-05")

    return SqliteCommitReader(db_path)


def test_sqlite_commit_reader_returns_empty_list_when_no_commits_stored(
    reader: SqliteCommitReader,
) -> None:
    result = reader.list_commits_for_repository("repo-1")

    assert result == []


def test_sqlite_commit_reader_returns_commits_for_repository(
    seeded_reader: SqliteCommitReader,
) -> None:
    result = seeded_reader.list_commits_for_repository("repo-1")

    assert len(result) == 3
    assert all(isinstance(c, CommitRecord) for c in result)
    assert all(c.repository_id == "repo-1" for c in result)


def test_sqlite_commit_reader_returns_commits_in_reverse_chronological_order(
    seeded_reader: SqliteCommitReader,
) -> None:
    result = seeded_reader.list_commits_for_repository("repo-1")

    assert result[0].sha == "aaa"
    assert result[1].sha == "bbb"
    assert result[2].sha == "ccc"


def test_sqlite_commit_reader_limits_result_when_limit_is_specified(
    seeded_reader: SqliteCommitReader,
) -> None:
    result = seeded_reader.list_commits_for_repository("repo-1", limit=2)

    assert len(result) == 2
    assert result[0].sha == "aaa"


def test_sqlite_commit_reader_isolates_commits_by_repository(
    seeded_reader: SqliteCommitReader,
) -> None:
    result = seeded_reader.list_commits_for_repository("repo-2")

    assert len(result) == 1
    assert result[0].sha == "xxx"
