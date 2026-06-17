"""Tests for new evidence and date-map readers on SQLite infrastructure."""

import sqlite3
from pathlib import Path

import pytest

from git_it.repository_ingestion.infrastructure.sqlite import (
    SqliteCommitFactStore,
    SqliteCommitReader,
    SqliteFileFactReader,
    SqliteFileFactStore,
)


def _seed_commit(
    conn: sqlite3.Connection,
    *,
    repository_id: str,
    sha: str,
    committed_at: str,
    message: str = "msg",
    author_name: str = "Alice",
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO commit_facts
            (repository_id, sha, committed_at, message, author_name, committer_name, parent_shas)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (repository_id, sha, committed_at, message, author_name, author_name, "[]"),
    )


def _seed_file(
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


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.sqlite3"
    SqliteCommitFactStore(path).initialize()
    SqliteFileFactStore(path).initialize()
    return path


# ---------------------------------------------------------------------------
# get_commit_date_map
# ---------------------------------------------------------------------------


def test_get_commit_date_map_returns_all_shas(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        _seed_commit(conn, repository_id="repo-1", sha="aaa111", committed_at="2024-01-01")
        _seed_commit(conn, repository_id="repo-1", sha="bbb222", committed_at="2024-03-01")
        conn.commit()
    date_map = SqliteCommitReader(db_path).get_commit_date_map("repo-1")
    assert date_map == {
        "aaa111": "2024-01-01",
        "bbb222": "2024-03-01",
    }


def test_get_commit_date_map_isolates_by_repository(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        _seed_commit(conn, repository_id="repo-1", sha="aaa111", committed_at="2024-01-01")
        _seed_commit(conn, repository_id="repo-2", sha="bbb222", committed_at="2024-03-01")
        conn.commit()
    date_map = SqliteCommitReader(db_path).get_commit_date_map("repo-1")
    assert "aaa111" in date_map
    assert "bbb222" not in date_map


def test_get_commit_date_map_returns_empty_for_unknown_repo(db_path: Path) -> None:
    date_map = SqliteCommitReader(db_path).get_commit_date_map("unknown")
    assert date_map == {}


# ---------------------------------------------------------------------------
# get_file_evidence_commits
# ---------------------------------------------------------------------------


def test_get_file_evidence_commits_returns_top_n_by_date(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        for i, date in enumerate(
            [
                "2024-01-01",
                "2024-02-01",
                "2024-03-01",
                "2024-04-01",
                "2024-05-01",
                "2024-06-01",
                "2024-07-01",
            ],
            start=1,
        ):
            sha = f"sha{i:03d}"
            _seed_commit(conn, repository_id="repo-1", sha=sha, committed_at=date)
            _seed_file(conn, repository_id="repo-1", commit_sha=sha, file_path="a.py")
        conn.commit()
    evidence = SqliteFileFactReader(db_path).get_file_evidence_commits("repo-1")
    shas = evidence.get("a.py", ())
    assert len(shas) == 5  # default limit=5
    # most recent 5: sha007 through sha003
    assert shas[0] == "sha007"
    assert shas[4] == "sha003"


def test_get_file_evidence_commits_respects_limit(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        for i, date in enumerate(["2024-01-01", "2024-02-01", "2024-03-01"], start=1):
            sha = f"sha{i:03d}"
            _seed_commit(conn, repository_id="repo-1", sha=sha, committed_at=date)
            _seed_file(conn, repository_id="repo-1", commit_sha=sha, file_path="b.py")
        conn.commit()
    evidence = SqliteFileFactReader(db_path).get_file_evidence_commits("repo-1", limit=2)
    shas = evidence.get("b.py", ())
    assert len(shas) == 2
    assert shas[0] == "sha003"  # most recent first


def test_get_file_evidence_commits_handles_multiple_files(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        _seed_commit(conn, repository_id="repo-1", sha="s1", committed_at="2024-01-01")
        _seed_commit(conn, repository_id="repo-1", sha="s2", committed_at="2024-02-01")
        _seed_file(conn, repository_id="repo-1", commit_sha="s1", file_path="a.py")
        _seed_file(conn, repository_id="repo-1", commit_sha="s2", file_path="b.py")
        conn.commit()
    evidence = SqliteFileFactReader(db_path).get_file_evidence_commits("repo-1")
    assert "a.py" in evidence
    assert "b.py" in evidence
    assert evidence["a.py"] == ("s1",)
    assert evidence["b.py"] == ("s2",)


def test_get_file_evidence_commits_returns_empty_for_unknown_repo(db_path: Path) -> None:
    evidence = SqliteFileFactReader(db_path).get_file_evidence_commits("unknown")
    assert evidence == {}


def test_get_file_evidence_commits_isolates_by_repository(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        _seed_commit(conn, repository_id="repo-1", sha="s1", committed_at="2024-01-01")
        _seed_commit(conn, repository_id="repo-2", sha="s2", committed_at="2024-02-01")
        _seed_file(conn, repository_id="repo-1", commit_sha="s1", file_path="a.py")
        _seed_file(conn, repository_id="repo-2", commit_sha="s2", file_path="a.py")
        conn.commit()
    evidence = SqliteFileFactReader(db_path).get_file_evidence_commits("repo-1")
    assert evidence.get("a.py") == ("s1",)
