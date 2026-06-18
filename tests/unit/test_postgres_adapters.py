"""PostgreSQL adapter contract tests.

These tests verify that PostgreSQL adapters implement the same public contract as
their SQLite counterparts (insert + read roundtrips for key stores).

Tests are SKIPPED when DATABASE_URL is not set to a PostgreSQL URL, so the suite
passes locally without a database and runs in CI when a Postgres service is present.
"""

import os

import pytest

from git_it.repository_ingestion.application.ports import (
    CaseStudyRecord,
    CommitPersistenceResult,
    IngestionRunRecord,
)
from git_it.repository_ingestion.domain.analysis import CommitAnalysis
from git_it.repository_ingestion.domain.commits import ExtractedCommit
from git_it.repository_ingestion.domain.github_context import GithubContext
from git_it.repository_ingestion.infrastructure.postgres import (
    PostgresCaseStudyStore,
    PostgresCommitAnalysisStore,
    PostgresCommitStore,
    PostgresGithubContextCache,
    PostgresIngestionRunStore,
    initialize,
)

POSTGRES_URL = os.environ.get("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL.startswith("postgresql"),
    reason="DATABASE_URL not set to PostgreSQL — skipping Postgres adapter tests",
)


@pytest.fixture(scope="module")
def conninfo() -> str:
    return POSTGRES_URL


@pytest.fixture(autouse=True, scope="module")
def _init_schema(conninfo: str) -> None:
    """Run migrations once per test session."""
    initialize(conninfo)


# ---------------------------------------------------------------------------
# RED: ingestion run store roundtrip
# GREEN: PostgresIngestionRunStore.save / get
# ---------------------------------------------------------------------------


def test_postgres_ingestion_run_store_roundtrips_a_completed_run(conninfo: str) -> None:
    """save_ingestion_run + get_ingestion_run returns the same record."""
    store = PostgresIngestionRunStore(conninfo)
    record = IngestionRunRecord(
        run_id="pg-run-1",
        repository_id="pg-repo-1",
        canonical_url="https://github.com/owner/repo",
        status="COMPLETED",
        started_at="2026-06-18T10:00:00Z",
        completed_at="2026-06-18T10:01:00Z",
        error_code=None,
        error_stage=None,
        retryable=None,
        safe_message=None,
    )

    store.save_ingestion_run(record)
    retrieved = store.get_ingestion_run("pg-run-1")

    assert retrieved == record


# ---------------------------------------------------------------------------
# RED: commit fact store idempotency
# GREEN: PostgresCommitStore.save_commit_facts with ON CONFLICT DO NOTHING
# ---------------------------------------------------------------------------


def _make_commit(sha: str, message: str = "msg") -> ExtractedCommit:
    return ExtractedCommit(
        sha=sha,
        committed_at="2026-01-01T00:00:00+00:00",
        message=message,
        author_name="Author",
        committer_name="Committer",
        parent_shas=(),
    )


def test_postgres_commit_store_inserts_new_commits(conninfo: str) -> None:
    """First save inserts, second save reuses (ON CONFLICT DO NOTHING)."""
    store = PostgresCommitStore(conninfo)
    commits = [_make_commit("pg-sha-aaa"), _make_commit("pg-sha-bbb")]

    result = store.save_commit_facts(commits, repository_id="pg-repo-2")

    assert isinstance(result, CommitPersistenceResult)
    assert result.inserted == 2
    assert result.reused == 0


def test_postgres_commit_store_marks_duplicates_as_reused(conninfo: str) -> None:
    """Re-saving the same commits sets reused count correctly."""
    store = PostgresCommitStore(conninfo)
    commits = [_make_commit("pg-sha-ccc")]
    store.save_commit_facts(commits, repository_id="pg-repo-3")

    result = store.save_commit_facts(commits, repository_id="pg-repo-3")

    assert result.inserted == 0
    assert result.reused == 1


# ---------------------------------------------------------------------------
# RED: commit analysis store roundtrip
# GREEN: PostgresCommitAnalysisStore.save_analysis / get_analysis
# ---------------------------------------------------------------------------


def test_postgres_commit_analysis_store_roundtrips_analysis(conninfo: str) -> None:
    """save_analysis + get_analysis returns equivalent CommitAnalysis."""
    store = PostgresCommitAnalysisStore(conninfo)
    analysis = CommitAnalysis(
        commit_sha="pg-sha-analysis-001",
        category="feature",
        summary="Added new feature",
        confidence=0.95,
    )

    saved = store.save_analysis(analysis, repository_id="pg-repo-4")
    retrieved = store.get_analysis(repository_id="pg-repo-4", commit_sha="pg-sha-analysis-001")

    assert saved is True
    assert retrieved is not None
    assert retrieved.commit_sha == analysis.commit_sha
    assert retrieved.category == analysis.category


def test_postgres_commit_analysis_store_is_idempotent(conninfo: str) -> None:
    """Second save of the same analysis returns False (ON CONFLICT DO NOTHING)."""
    store = PostgresCommitAnalysisStore(conninfo)
    analysis = CommitAnalysis(
        commit_sha="pg-sha-analysis-002",
        category="refactor",
        summary="Cleaned up code",
        confidence=0.88,
    )
    store.save_analysis(analysis, repository_id="pg-repo-5")

    second_save = store.save_analysis(analysis, repository_id="pg-repo-5")

    assert second_save is False


# ---------------------------------------------------------------------------
# RED: case study store roundtrip
# GREEN: PostgresCaseStudyStore.save / get
# ---------------------------------------------------------------------------


def test_postgres_case_study_store_roundtrips_record(conninfo: str) -> None:
    """save_case_study + get_case_study returns matching record."""
    store = PostgresCaseStudyStore(conninfo)
    record = CaseStudyRecord(
        repository_id="pg-repo-6",
        narrative="This repo has a rich history.",
        commit_count=42,
        hotspot_count=3,
    )

    store.save_case_study(record)
    retrieved = store.get_case_study("pg-repo-6")

    assert retrieved is not None
    assert retrieved.repository_id == record.repository_id
    assert retrieved.narrative == record.narrative
    assert retrieved.commit_count == record.commit_count
    assert retrieved.hotspot_count == record.hotspot_count


# ---------------------------------------------------------------------------
# RED: github context cache miss / hit
# GREEN: PostgresGithubContextCache.is_cached / get_cached / save
# ---------------------------------------------------------------------------


def test_postgres_github_context_cache_miss_before_save(conninfo: str) -> None:
    """is_cached returns False before any save for a new commit."""
    cache = PostgresGithubContextCache(conninfo)
    assert cache.is_cached("pg-repo-7", "pg-sha-never-seen") is False


def test_postgres_github_context_cache_hit_after_save(conninfo: str) -> None:
    """is_cached returns True after saving a positive context."""
    cache = PostgresGithubContextCache(conninfo)
    context = GithubContext(
        pr_number=101,
        pr_title="Add PostgreSQL support",
        pr_body="Full description here.",
        issue_numbers=(42,),
        issue_bodies=("Issue body",),
        has_pr=True,
    )

    cache.save("pg-repo-8", "pg-sha-with-pr", context)

    assert cache.is_cached("pg-repo-8", "pg-sha-with-pr") is True
    retrieved = cache.get_cached("pg-repo-8", "pg-sha-with-pr")
    assert retrieved is not None
    assert retrieved.pr_number == 101
    assert retrieved.pr_title == "Add PostgreSQL support"
