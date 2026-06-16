import sqlite3
from pathlib import Path

import pytest

from git_it.repository_ingestion.infrastructure.sqlite import (
    SqliteFileFactReader,
    SqliteFileFactStore,
)


def _seed(
    conn: sqlite3.Connection,
    *,
    repository_id: str,
    commit_sha: str,
    file_path: str,
    insertions: int = 5,
    deletions: int = 3,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO file_facts
            (repository_id, commit_sha, file_path, insertions, deletions)
        VALUES (?, ?, ?, ?, ?)
        """,
        (repository_id, commit_sha, file_path, insertions, deletions),
    )
    conn.commit()


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.sqlite3"
    SqliteFileFactStore(path).initialize()
    return path


def test_get_file_churn_returns_empty_for_unknown_repo(db_path: Path) -> None:
    assert SqliteFileFactReader(db_path).get_file_churn("unknown-repo") == []


def test_get_file_churn_aggregates_insertions_and_deletions(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        _seed(
            conn,
            repository_id="repo-1",
            commit_sha="sha1",
            file_path="a.py",
            insertions=10,
            deletions=5,
        )
        _seed(
            conn,
            repository_id="repo-1",
            commit_sha="sha2",
            file_path="a.py",
            insertions=3,
            deletions=2,
        )
    records = SqliteFileFactReader(db_path).get_file_churn("repo-1")
    assert len(records) == 1
    assert records[0].file_path == "a.py"
    assert records[0].total_insertions == 13
    assert records[0].total_deletions == 7


def test_get_file_churn_counts_distinct_commits(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        _seed(conn, repository_id="repo-1", commit_sha="sha1", file_path="a.py")
        _seed(conn, repository_id="repo-1", commit_sha="sha2", file_path="a.py")
        _seed(conn, repository_id="repo-1", commit_sha="sha3", file_path="a.py")
    records = SqliteFileFactReader(db_path).get_file_churn("repo-1")
    assert records[0].commit_count == 3


def test_get_file_churn_isolates_by_repository(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        _seed(conn, repository_id="repo-1", commit_sha="sha1", file_path="a.py")
        _seed(conn, repository_id="repo-2", commit_sha="sha2", file_path="b.py")
    records = SqliteFileFactReader(db_path).get_file_churn("repo-1")
    assert len(records) == 1
    assert records[0].file_path == "a.py"


def test_get_file_churn_sorted_by_commit_count_descending(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        for sha, path in [("sha1", "rare.py"), ("sha2", "common.py"), ("sha3", "common.py")]:
            _seed(conn, repository_id="repo-1", commit_sha=sha, file_path=path)
    records = SqliteFileFactReader(db_path).get_file_churn("repo-1")
    assert records[0].file_path == "common.py"
    assert records[0].commit_count == 2
