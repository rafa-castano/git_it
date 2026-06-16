from pathlib import Path

import pytest

from git_it.repository_ingestion.domain.analysis import (
    CommitAnalysis,
    CommitCategory,
    RiskLevel,
)
from git_it.repository_ingestion.infrastructure.sqlite import (
    SqliteCommitAnalysisStore,
    SqliteFileFactStore,
)


def _make_analysis(sha: str = "abc1234", summary: str = "Added feature") -> CommitAnalysis:
    return CommitAnalysis(
        commit_sha=sha,
        summary=summary,
        category=CommitCategory.FEATURE,
        intent=None,
        intent_is_inferred=True,
        affected_components=["core"],
        risk_level=RiskLevel.LOW,
        confidence=0.8,
        evidence=[],
        limitations=[],
    )


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.sqlite3"
    SqliteFileFactStore(path).initialize()
    store = SqliteCommitAnalysisStore(path)
    store.initialize()
    return path


def test_save_analysis_inserts_new_row_and_returns_true(db_path: Path) -> None:
    store = SqliteCommitAnalysisStore(db_path)
    result = store.save_analysis(_make_analysis("sha1"), repository_id="repo-1")
    assert result is True


def test_save_analysis_duplicate_returns_false(db_path: Path) -> None:
    store = SqliteCommitAnalysisStore(db_path)
    store.save_analysis(_make_analysis("sha1"), repository_id="repo-1")
    result = store.save_analysis(_make_analysis("sha1"), repository_id="repo-1")
    assert result is False


def test_get_analysis_returns_stored_analysis(db_path: Path) -> None:
    store = SqliteCommitAnalysisStore(db_path)
    original = _make_analysis("sha1", "Fixed bug")
    store.save_analysis(original, repository_id="repo-1")
    retrieved = store.get_analysis(repository_id="repo-1", commit_sha="sha1")
    assert retrieved is not None
    assert retrieved.commit_sha == "sha1"
    assert retrieved.summary == "Fixed bug"
    assert retrieved.category == CommitCategory.FEATURE


def test_get_analysis_returns_none_when_not_found(db_path: Path) -> None:
    store = SqliteCommitAnalysisStore(db_path)
    assert store.get_analysis(repository_id="repo-1", commit_sha="unknown") is None


def test_list_analyses_returns_all_for_repository(db_path: Path) -> None:
    store = SqliteCommitAnalysisStore(db_path)
    store.save_analysis(_make_analysis("sha1"), repository_id="repo-1")
    store.save_analysis(_make_analysis("sha2"), repository_id="repo-1")
    results = store.list_analyses("repo-1")
    assert len(results) == 2


def test_list_analyses_isolates_by_repository(db_path: Path) -> None:
    store = SqliteCommitAnalysisStore(db_path)
    store.save_analysis(_make_analysis("sha1"), repository_id="repo-1")
    store.save_analysis(_make_analysis("sha2"), repository_id="repo-2")
    assert len(store.list_analyses("repo-1")) == 1
    assert len(store.list_analyses("repo-2")) == 1


def test_list_analyses_respects_limit(db_path: Path) -> None:
    store = SqliteCommitAnalysisStore(db_path)
    for i in range(5):
        store.save_analysis(_make_analysis(f"sha{i}"), repository_id="repo-1")
    assert len(store.list_analyses("repo-1", limit=3)) == 3
