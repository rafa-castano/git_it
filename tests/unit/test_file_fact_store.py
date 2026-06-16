from pathlib import Path

import pytest

from git_it.repository_ingestion.domain.commits import ExtractedCommit, ExtractedFileChange
from git_it.repository_ingestion.infrastructure.sqlite import SqliteFileFactStore


def _make_commit(sha: str, files: list[tuple[str, int, int]]) -> ExtractedCommit:
    return ExtractedCommit(
        sha=sha,
        committed_at="2026-01-01T00:00:00+00:00",
        message="commit",
        author_name="Author",
        committer_name="Committer",
        parent_shas=(),
        file_changes=tuple(
            ExtractedFileChange(path=path, insertions=ins, deletions=dlt)
            for path, ins, dlt in files
        ),
    )


@pytest.fixture()
def store(tmp_path: Path) -> SqliteFileFactStore:
    s = SqliteFileFactStore(tmp_path / "git-it.db")
    s.initialize()
    return s


def test_sqlite_file_fact_store_inserts_new_file_facts(
    store: SqliteFileFactStore,
) -> None:
    commits = [
        _make_commit("aaa", [("src/a.py", 10, 0)]),
        _make_commit("bbb", [("src/b.py", 5, 2), ("src/c.py", 3, 0)]),
    ]

    result = store.save_file_facts(commits, repository_id="repo-1")

    assert result.inserted == 3
    assert result.reused == 0


def test_sqlite_file_fact_store_marks_existing_file_facts_as_reused_on_reingest(
    store: SqliteFileFactStore,
) -> None:
    commits = [
        _make_commit("aaa", [("src/a.py", 10, 0)]),
        _make_commit("bbb", [("src/b.py", 5, 2)]),
    ]
    store.save_file_facts(commits, repository_id="repo-1")

    result = store.save_file_facts(commits, repository_id="repo-1")

    assert result.inserted == 0
    assert result.reused == 2


def test_sqlite_file_fact_store_tracks_mixed_insertions_and_reuses(
    store: SqliteFileFactStore,
) -> None:
    first_commits = [_make_commit("aaa", [("src/a.py", 10, 0)])]
    store.save_file_facts(first_commits, repository_id="repo-1")

    second_commits = [
        _make_commit("aaa", [("src/a.py", 10, 0)]),
        _make_commit("bbb", [("src/b.py", 5, 2)]),
    ]
    result = store.save_file_facts(second_commits, repository_id="repo-1")

    assert result.inserted == 1
    assert result.reused == 1


def test_sqlite_file_fact_store_treats_same_file_as_independent_across_repositories(
    store: SqliteFileFactStore,
) -> None:
    commits = [_make_commit("aaa", [("src/a.py", 10, 0)])]

    result_a = store.save_file_facts(commits, repository_id="repo-1")
    result_b = store.save_file_facts(commits, repository_id="repo-2")

    assert result_a.inserted == 1
    assert result_b.inserted == 1


def test_sqlite_file_fact_store_skips_commits_with_no_file_changes(
    store: SqliteFileFactStore,
) -> None:
    commits = [_make_commit("aaa", [])]

    result = store.save_file_facts(commits, repository_id="repo-1")

    assert result.inserted == 0
    assert result.reused == 0
