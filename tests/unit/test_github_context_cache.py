"""Tests for SqliteGithubContextCache — RED phase.

Each test covers one observable behavior of the cache:
- cache miss (not fetched)
- negative cache entry (fetched, no PR)
- positive cache entry (fetched, PR found)
- idempotent save
- table initialization
"""

from pathlib import Path

import pytest

from git_it.repository_ingestion.domain.github_context import GithubContext
from git_it.repository_ingestion.infrastructure.sqlite import SqliteGithubContextCache


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.sqlite3"


@pytest.fixture()
def cache(db_path: Path) -> SqliteGithubContextCache:
    c = SqliteGithubContextCache(db_path)
    c.initialize()
    return c


def test_initialize_creates_table(db_path: Path) -> None:
    """initialize() must create the github_context table."""
    import sqlite3

    c = SqliteGithubContextCache(db_path)
    c.initialize()
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='github_context'"
        ).fetchone()
    assert row is not None


def test_cache_miss_returns_not_fetched(cache: SqliteGithubContextCache) -> None:
    """A SHA with no row in the table must report is_cached=False."""
    assert cache.is_cached("repo-1", "abc123") is False


def test_save_negative_entry_marks_as_tried(cache: SqliteGithubContextCache) -> None:
    """After save(context=None), is_cached must be True and get_cached must return None."""
    cache.save("repo-1", "abc123", None)
    assert cache.is_cached("repo-1", "abc123") is True
    assert cache.get_cached("repo-1", "abc123") is None


def test_save_positive_entry_returns_data(cache: SqliteGithubContextCache) -> None:
    """After save(context=GithubContext(...)), get_cached must return the same context."""
    ctx = GithubContext(
        pr_number=42,
        pr_title="My PR",
        pr_body="Fixes #7",
        issue_numbers=(7,),
        issue_bodies=("Issue body here",),
        has_pr=True,
    )
    cache.save("repo-1", "abc123", ctx)
    assert cache.is_cached("repo-1", "abc123") is True
    result = cache.get_cached("repo-1", "abc123")
    assert result is not None
    assert result.pr_number == 42
    assert result.pr_title == "My PR"
    assert result.pr_body == "Fixes #7"
    assert result.issue_numbers == (7,)
    assert result.issue_bodies == ("Issue body here",)
    assert result.has_pr is True


def test_idempotent_save_does_not_raise(cache: SqliteGithubContextCache) -> None:
    """Saving the same SHA twice must not raise any error."""
    ctx = GithubContext(pr_number=1, pr_title="PR", has_pr=True)
    cache.save("repo-1", "abc123", ctx)
    # Second save with same key must be a no-op without raising.
    cache.save("repo-1", "abc123", ctx)
    result = cache.get_cached("repo-1", "abc123")
    assert result is not None
    assert result.pr_number == 1
