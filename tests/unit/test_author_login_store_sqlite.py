"""Tests for SqliteAuthorLoginStore — author-email -> GitHub-login persistence (spec 031)."""

import sqlite3
from pathlib import Path

import pytest

from git_it.repository_ingestion.infrastructure.sqlite import SqliteAuthorLoginStore


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "author_logins_test.sqlite3"
    SqliteAuthorLoginStore(path).initialize()
    return path


def test_get_returns_empty_for_unknown_repo(db_path: Path) -> None:
    assert SqliteAuthorLoginStore(db_path).get_author_logins("repo-unknown") == {}


def test_save_and_get_roundtrips_logins_and_null_markers(db_path: Path) -> None:
    store = SqliteAuthorLoginStore(db_path)
    mapping: dict[str, str | None] = {
        "alice@example.com": "alice-gh",
        "nomatch@example.com": None,  # attempted, no match
    }
    store.save_author_logins("repo-1", mapping)
    assert store.get_author_logins("repo-1") == mapping


def test_resave_overwrites_null_marker_with_login(db_path: Path) -> None:
    store = SqliteAuthorLoginStore(db_path)
    store.save_author_logins("repo-1", {"bob@example.com": None})
    store.save_author_logins("repo-1", {"bob@example.com": "bob-gh"})
    assert store.get_author_logins("repo-1") == {"bob@example.com": "bob-gh"}


def test_different_repos_are_independent(db_path: Path) -> None:
    store = SqliteAuthorLoginStore(db_path)
    store.save_author_logins("repo-1", {"a@example.com": "a-gh"})
    store.save_author_logins("repo-2", {"b@example.com": "b-gh"})
    assert store.get_author_logins("repo-1") == {"a@example.com": "a-gh"}
    assert store.get_author_logins("repo-2") == {"b@example.com": "b-gh"}


def test_empty_mapping_is_a_noop(db_path: Path) -> None:
    store = SqliteAuthorLoginStore(db_path)
    store.save_author_logins("repo-1", {})
    assert store.get_author_logins("repo-1") == {}


def test_read_distinct_author_emails(db_path: Path) -> None:
    # commit_facts is created by the commit store; build a minimal one here.
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS commit_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repository_id TEXT NOT NULL,
                sha TEXT NOT NULL,
                committed_at TEXT NOT NULL,
                message TEXT NOT NULL,
                author_name TEXT NOT NULL,
                committer_name TEXT NOT NULL,
                parent_shas TEXT NOT NULL,
                author_email TEXT NOT NULL DEFAULT '',
                UNIQUE(repository_id, sha)
            )
            """
        )
        conn.executemany(
            "INSERT INTO commit_facts (repository_id, sha, committed_at, message,"
            " author_name, committer_name, parent_shas, author_email)"
            " VALUES (?, ?, '2024-01-01', 'm', 'A', 'A', '[]', ?)",
            [
                ("repo-1", "s1", "alice@example.com"),
                ("repo-1", "s2", "alice@example.com"),  # duplicate email
                ("repo-1", "s3", "bob@example.com"),
                ("repo-1", "s4", ""),  # empty email excluded
                ("repo-2", "s5", "carol@example.com"),  # other repo excluded
            ],
        )
        conn.commit()

    store = SqliteAuthorLoginStore(db_path)
    assert store.read_distinct_author_emails("repo-1") == {
        "alice@example.com",
        "bob@example.com",
    }
    assert store.read_distinct_author_emails("repo-unknown") == set()
