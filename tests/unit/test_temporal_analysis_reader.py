from pathlib import Path

import pytest

from git_it.repository_ingestion.application.ports import TimestampedAnalysis
from git_it.repository_ingestion.domain.analysis import (
    CommitAnalysis,
    CommitCategory,
    RiskLevel,
)
from git_it.repository_ingestion.domain.commits import ExtractedCommit
from git_it.repository_ingestion.infrastructure.sqlite import (
    SqliteCommitAnalysisStore,
    SqliteCommitFactStore,
)


def _analysis(sha: str) -> CommitAnalysis:
    return CommitAnalysis(
        commit_sha=sha,
        summary="summary",
        category=CommitCategory.FEATURE,
        confidence=0.8,
        risk_level=RiskLevel.LOW,
        intent=None,
        intent_is_inferred=False,
        affected_components=[],
        evidence=[],
        limitations=[],
    )


def _commit(sha: str, committed_at: str) -> ExtractedCommit:
    return ExtractedCommit(
        sha=sha,
        committed_at=committed_at,
        message="msg",
        author_name="author",
        committer_name="committer",
        parent_shas=(),
        file_changes=(),
    )


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.sqlite3"
    SqliteCommitFactStore(path).initialize()
    store = SqliteCommitAnalysisStore(path)
    store.initialize()
    return path


def test_list_analyses_with_dates_returns_empty_when_no_analyses(db_path: Path) -> None:
    store = SqliteCommitAnalysisStore(db_path)
    result = store.list_analyses_with_dates("repo-1")
    assert result == []


def test_list_analyses_with_dates_returns_timestamped_analysis(db_path: Path) -> None:
    fact_store = SqliteCommitFactStore(db_path)
    fact_store.save_commit_facts([_commit("sha1", "2024-03-01T10:00:00")], repository_id="repo-1")

    analysis_store = SqliteCommitAnalysisStore(db_path)
    analysis_store.save_analysis(_analysis("sha1"), repository_id="repo-1")

    result = analysis_store.list_analyses_with_dates("repo-1")
    assert len(result) == 1
    assert isinstance(result[0], TimestampedAnalysis)
    assert result[0].analysis.commit_sha == "sha1"
    assert "2024-03-01" in result[0].committed_at


def test_list_analyses_with_dates_ordered_chronologically(db_path: Path) -> None:
    fact_store = SqliteCommitFactStore(db_path)
    fact_store.save_commit_facts(
        [
            _commit("sha1", "2024-01-01T00:00:00"),
            _commit("sha2", "2024-06-01T00:00:00"),
            _commit("sha3", "2024-03-01T00:00:00"),
        ],
        repository_id="repo-1",
    )
    store = SqliteCommitAnalysisStore(db_path)
    for sha in ("sha1", "sha2", "sha3"):
        store.save_analysis(_analysis(sha), repository_id="repo-1")

    result = store.list_analyses_with_dates("repo-1")
    shas = [r.analysis.commit_sha for r in result]
    assert shas == ["sha1", "sha3", "sha2"]


def test_list_analyses_with_dates_excludes_unmatched_commits(db_path: Path) -> None:
    fact_store = SqliteCommitFactStore(db_path)
    fact_store.save_commit_facts([_commit("sha1", "2024-01-01T00:00:00")], repository_id="repo-1")

    store = SqliteCommitAnalysisStore(db_path)
    store.save_analysis(_analysis("sha1"), repository_id="repo-1")
    store.save_analysis(_analysis("sha_no_fact"), repository_id="repo-1")

    result = store.list_analyses_with_dates("repo-1")
    assert len(result) == 1
    assert result[0].analysis.commit_sha == "sha1"
