from pathlib import Path

import pytest

from git_it.repository_ingestion.domain.commits import ExtractedCommit
from git_it.repository_ingestion.infrastructure.sqlite import SqliteCommitFactStore


def _make_commit(sha: str, message: str = "commit") -> ExtractedCommit:
    return ExtractedCommit(
        sha=sha,
        committed_at="2026-01-01T00:00:00+00:00",
        message=message,
        author_name="Author",
        committer_name="Committer",
        parent_shas=(),
    )


@pytest.fixture()
def store(tmp_path: Path) -> SqliteCommitFactStore:
    s = SqliteCommitFactStore(tmp_path / "git-it.db")
    s.initialize()
    return s


def test_sqlite_commit_fact_store_inserts_new_commits(
    store: SqliteCommitFactStore,
) -> None:
    commits = [_make_commit("aaa"), _make_commit("bbb"), _make_commit("ccc")]

    result = store.save_commit_facts(commits, repository_id="repo-1")

    assert result.inserted == 3
    assert result.reused == 0


def test_sqlite_commit_fact_store_marks_existing_commits_as_reused_on_reingest(
    store: SqliteCommitFactStore,
) -> None:
    commits = [_make_commit("aaa"), _make_commit("bbb"), _make_commit("ccc")]
    store.save_commit_facts(commits, repository_id="repo-1")

    result = store.save_commit_facts(commits, repository_id="repo-1")

    assert result.inserted == 0
    assert result.reused == 3


def test_sqlite_commit_fact_store_tracks_mixed_insertions_and_reuses(
    store: SqliteCommitFactStore,
) -> None:
    store.save_commit_facts([_make_commit("aaa"), _make_commit("bbb")], repository_id="repo-1")

    result = store.save_commit_facts(
        [_make_commit("aaa"), _make_commit("bbb"), _make_commit("ccc")],
        repository_id="repo-1",
    )

    assert result.inserted == 1
    assert result.reused == 2


def test_sqlite_commit_fact_store_treats_same_sha_as_independent_across_repositories(
    store: SqliteCommitFactStore,
) -> None:
    result_a = store.save_commit_facts([_make_commit("aaa")], repository_id="repo-1")
    result_b = store.save_commit_facts([_make_commit("aaa")], repository_id="repo-2")

    assert result_a.inserted == 1
    assert result_b.inserted == 1
