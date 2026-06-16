"""Tests for SqliteCommitReader ordering, since, and until filtering."""

from pathlib import Path

from git_it.repository_ingestion.domain.commits import ExtractedCommit
from git_it.repository_ingestion.infrastructure.sqlite import (
    SqliteCommitFactStore,
    SqliteCommitReader,
)


def _make_commit(sha: str, committed_at: str, message: str) -> ExtractedCommit:
    return ExtractedCommit(
        sha=sha,
        committed_at=committed_at,
        message=message,
        author_name="A",
        committer_name="A",
        parent_shas=(),
        file_changes=(),
    )


def _setup_reader(tmp_path: Path) -> tuple[SqliteCommitReader, list[str]]:
    db_path = tmp_path / "test.sqlite3"
    store = SqliteCommitFactStore(db_path)
    store.initialize()
    commits = [
        _make_commit("sha-old", "2024-01-01T00:00:00+00:00", "Oldest"),
        _make_commit("sha-mid", "2024-06-01T00:00:00+00:00", "Middle"),
        _make_commit("sha-new", "2024-12-01T00:00:00+00:00", "Newest"),
    ]
    store.save_commit_facts(commits, repository_id="repo-1")
    reader = SqliteCommitReader(db_path)
    return reader, ["sha-old", "sha-mid", "sha-new"]


def test_default_order_returns_newest_first(tmp_path: Path) -> None:
    reader, _ = _setup_reader(tmp_path)
    results = reader.list_commits_for_repository("repo-1")
    assert results[0].sha == "sha-new"


def test_order_oldest_returns_oldest_first(tmp_path: Path) -> None:
    reader, _ = _setup_reader(tmp_path)
    results = reader.list_commits_for_repository("repo-1", order="oldest")
    assert results[0].sha == "sha-old"


def test_order_newest_returns_newest_first(tmp_path: Path) -> None:
    reader, _ = _setup_reader(tmp_path)
    results = reader.list_commits_for_repository("repo-1", order="newest")
    assert results[0].sha == "sha-new"


def test_since_excludes_commits_before_date(tmp_path: Path) -> None:
    reader, _ = _setup_reader(tmp_path)
    results = reader.list_commits_for_repository("repo-1", since="2024-06-01")
    shas = [r.sha for r in results]
    assert "sha-old" not in shas
    assert "sha-mid" in shas
    assert "sha-new" in shas


def test_until_excludes_commits_after_date(tmp_path: Path) -> None:
    reader, _ = _setup_reader(tmp_path)
    results = reader.list_commits_for_repository("repo-1", until="2024-06-01")
    shas = [r.sha for r in results]
    assert "sha-new" not in shas
    assert "sha-old" in shas
    assert "sha-mid" in shas


def test_since_and_until_range(tmp_path: Path) -> None:
    reader, _ = _setup_reader(tmp_path)
    results = reader.list_commits_for_repository("repo-1", since="2024-06-01", until="2024-06-01")
    assert len(results) == 1
    assert results[0].sha == "sha-mid"


def test_limit_with_oldest_order(tmp_path: Path) -> None:
    reader, _ = _setup_reader(tmp_path)
    results = reader.list_commits_for_repository("repo-1", order="oldest", limit=2)
    shas = [r.sha for r in results]
    assert shas == ["sha-old", "sha-mid"]


def test_limit_with_newest_order(tmp_path: Path) -> None:
    reader, _ = _setup_reader(tmp_path)
    results = reader.list_commits_for_repository("repo-1", order="newest", limit=2)
    shas = [r.sha for r in results]
    assert shas == ["sha-new", "sha-mid"]


def test_since_with_oldest_order(tmp_path: Path) -> None:
    reader, _ = _setup_reader(tmp_path)
    results = reader.list_commits_for_repository("repo-1", since="2024-06-01", order="oldest")
    assert results[0].sha == "sha-mid"


def test_no_results_when_since_is_future(tmp_path: Path) -> None:
    reader, _ = _setup_reader(tmp_path)
    results = reader.list_commits_for_repository("repo-1", since="2099-01-01")
    assert results == []
