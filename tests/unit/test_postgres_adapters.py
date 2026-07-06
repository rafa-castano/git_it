"""PostgreSQL adapter contract tests.

These tests verify that PostgreSQL adapters implement the same public contract as
their SQLite counterparts (insert + read roundtrips for key stores).

Tests are SKIPPED when DATABASE_URL is not set to a PostgreSQL URL, so the suite
passes locally without a database and runs in CI when a Postgres service is present.
"""

import os
from datetime import UTC, datetime

import pytest

from git_it.repository_ingestion.application.ports import (
    CaseStudyRecord,
    CommitPersistenceResult,
    IngestionRunRecord,
)
from git_it.repository_ingestion.domain.advisories import AdvisoryEvidence
from git_it.repository_ingestion.domain.analysis import CommitAnalysis, CommitCategory
from git_it.repository_ingestion.domain.commits import ExtractedCommit, ExtractedFileChange
from git_it.repository_ingestion.domain.discussions import DiscussionEvidence
from git_it.repository_ingestion.domain.embeddings import EmbeddedChunk
from git_it.repository_ingestion.domain.github_context import GithubContext
from git_it.repository_ingestion.domain.project_docs import ProjectDocContent
from git_it.repository_ingestion.domain.releases import ReleaseEvidence
from git_it.repository_ingestion.domain.repo_metadata import LanguageBreakdown, RepoMetadata
from git_it.repository_ingestion.infrastructure.postgres import (
    PostgresAdvisoryEvidenceStore,
    PostgresCaseStudyStore,
    PostgresCommitAnalysisStore,
    PostgresCommitStore,
    PostgresCommitWithAnalysisReader,
    PostgresDefaultBranchStore,
    PostgresDiscussionEvidenceStore,
    PostgresEmbeddingStore,
    PostgresFileFactStore,
    PostgresGithubContextCache,
    PostgresIngestionRunStore,
    PostgresProjectDocStore,
    PostgresReleaseEvidenceStore,
    PostgresRepoMetadataStore,
    PostgresRepositoryDeleter,
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
        category=CommitCategory.FEATURE,
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
        category=CommitCategory.REFACTOR,
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


# ---------------------------------------------------------------------------
# Spec 014 — Postgres read-layer parity for the API endpoints
# ---------------------------------------------------------------------------


def test_postgres_case_study_store_lists_available_audiences(conninfo: str) -> None:
    """list_available_audiences returns distinct audiences, mirroring SQLite."""
    store = PostgresCaseStudyStore(conninfo)
    for audience in ("beginner", "expert"):
        store.save_case_study(
            CaseStudyRecord(
                repository_id="pg-repo-9",
                narrative="Narrative text.",
                commit_count=1,
                hotspot_count=0,
                audience=audience,
            )
        )

    audiences = store.list_available_audiences("pg-repo-9")

    assert audiences == ["beginner", "expert"]


def _seed_analyzed_commit(
    conninfo: str,
    *,
    repository_id: str,
    sha: str,
    category: CommitCategory,
    file_path: str | None = None,
) -> None:
    file_changes = (
        (ExtractedFileChange(path=file_path, insertions=1, deletions=1),) if file_path else ()
    )
    commit = ExtractedCommit(
        sha=sha,
        committed_at="2026-01-01T00:00:00+00:00",
        message="msg",
        author_name="Author",
        committer_name="Committer",
        parent_shas=(),
        file_changes=file_changes,
    )
    PostgresCommitStore(conninfo).save_commit_facts([commit], repository_id=repository_id)
    PostgresFileFactStore(conninfo).save_file_facts([commit], repository_id=repository_id)
    PostgresCommitAnalysisStore(conninfo).save_analysis(
        CommitAnalysis(commit_sha=sha, category=category, summary="s", confidence=0.9),
        repository_id=repository_id,
    )


def test_postgres_commit_with_analysis_reader_counts_and_filters_by_category(
    conninfo: str,
) -> None:
    """count/list honour the category filter, mirroring the SQLite contract."""
    _seed_analyzed_commit(
        conninfo, repository_id="pg-repo-10", sha="pg-sha-cat-1", category=CommitCategory.DOCS
    )
    _seed_analyzed_commit(
        conninfo, repository_id="pg-repo-10", sha="pg-sha-cat-2", category=CommitCategory.FEATURE
    )
    reader = PostgresCommitWithAnalysisReader(conninfo)

    assert reader.count_commits_with_analyses("pg-repo-10") == 2
    assert reader.count_commits_with_analyses("pg-repo-10", category="docs") == 1
    filtered = reader.list_commits_with_analyses("pg-repo-10", limit=10, category="docs")
    assert [record.sha for record in filtered] == ["pg-sha-cat-1"]


def test_postgres_commit_with_analysis_reader_returns_files_changed(conninfo: str) -> None:
    """files_changed is aggregated from file_facts, mirroring the SQLite contract."""
    _seed_analyzed_commit(
        conninfo,
        repository_id="pg-repo-11",
        sha="pg-sha-files-1",
        category=CommitCategory.FEATURE,
        file_path="src/main.py",
    )
    reader = PostgresCommitWithAnalysisReader(conninfo)

    records = reader.list_commits_with_analyses("pg-repo-11", limit=10)

    assert records[0].files_changed == ("src/main.py",)


def test_postgres_repository_deleter_removes_all_repository_rows(conninfo: str) -> None:
    """delete_repository removes ingestion runs, facts, and analyses for the repo."""
    run_store = PostgresIngestionRunStore(conninfo)
    run_store.save_ingestion_run(
        IngestionRunRecord(
            run_id="pg-run-del-1",
            repository_id="pg-repo-12",
            canonical_url="https://github.com/owner/repo",
            status="COMPLETED",
            started_at="2026-06-18T10:00:00Z",
            completed_at=None,
            error_code=None,
            error_stage=None,
            retryable=None,
            safe_message=None,
        )
    )
    _seed_analyzed_commit(
        conninfo,
        repository_id="pg-repo-12",
        sha="pg-sha-del-1",
        category=CommitCategory.FEATURE,
        file_path="src/main.py",
    )

    PostgresRepositoryDeleter(conninfo).delete_repository("pg-repo-12")

    assert run_store.list_ingestion_runs_for_repository("pg-repo-12") == []
    reader = PostgresCommitWithAnalysisReader(conninfo)
    assert reader.count_commits_with_analyses("pg-repo-12") == 0


# ---------------------------------------------------------------------------
# Spec 019 — GitHub stars + language breakdown repo-metadata store
# ---------------------------------------------------------------------------


def test_postgres_repo_metadata_store_returns_none_when_absent(conninfo: str) -> None:
    store = PostgresRepoMetadataStore(conninfo)
    assert store.get_repo_metadata("pg-repo-13") is None


def test_postgres_repo_metadata_store_roundtrips_stars_and_languages(conninfo: str) -> None:
    store = PostgresRepoMetadataStore(conninfo)
    metadata = RepoMetadata(
        stars=1234,
        languages=(
            LanguageBreakdown(language="Python", bytes=300),
            LanguageBreakdown(language="HTML", bytes=100),
        ),
    )

    store.save_repo_metadata("pg-repo-14", metadata)
    retrieved = store.get_repo_metadata("pg-repo-14")

    assert retrieved == metadata


def test_postgres_repo_metadata_store_upsert_overwrites(conninfo: str) -> None:
    store = PostgresRepoMetadataStore(conninfo)
    store.save_repo_metadata("pg-repo-15", RepoMetadata(stars=1, languages=()))

    store.save_repo_metadata(
        "pg-repo-15",
        RepoMetadata(stars=99, languages=(LanguageBreakdown(language="Go", bytes=50),)),
    )

    assert store.get_repo_metadata("pg-repo-15") == RepoMetadata(
        stars=99, languages=(LanguageBreakdown(language="Go", bytes=50),)
    )


# ---------------------------------------------------------------------------
# Spec 020 — default branch store
# ---------------------------------------------------------------------------


def test_postgres_default_branch_store_returns_none_when_absent(conninfo: str) -> None:
    store = PostgresDefaultBranchStore(conninfo)
    assert store.get_default_branch("pg-repo-16") is None


def test_postgres_default_branch_store_roundtrips(conninfo: str) -> None:
    store = PostgresDefaultBranchStore(conninfo)
    store.save_default_branch("pg-repo-17", "main")
    assert store.get_default_branch("pg-repo-17") == "main"


def test_postgres_default_branch_store_upsert_overwrites(conninfo: str) -> None:
    store = PostgresDefaultBranchStore(conninfo)
    store.save_default_branch("pg-repo-18", "main")
    store.save_default_branch("pg-repo-18", "develop")
    assert store.get_default_branch("pg-repo-18") == "develop"


# ---------------------------------------------------------------------------
# Spec 025 — project doc store
# ---------------------------------------------------------------------------


def test_postgres_project_doc_store_returns_none_when_absent(conninfo: str) -> None:
    store = PostgresProjectDocStore(conninfo)
    assert store.get_project_docs("pg-repo-19") is None


def test_postgres_project_doc_store_roundtrips(conninfo: str) -> None:
    store = PostgresProjectDocStore(conninfo)
    content = ProjectDocContent(
        repository_id="pg-repo-20",
        readme_text="# Hello",
        readme_truncated=False,
        changelog_text="## v1.0.0",
        changelog_truncated=True,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    store.save_project_docs(content)
    assert store.get_project_docs("pg-repo-20") == content


def test_postgres_project_doc_store_upsert_overwrites(conninfo: str) -> None:
    store = PostgresProjectDocStore(conninfo)
    first = ProjectDocContent(
        repository_id="pg-repo-21",
        readme_text="first",
        readme_truncated=False,
        changelog_text=None,
        changelog_truncated=False,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    second = ProjectDocContent(
        repository_id="pg-repo-21",
        readme_text="second",
        readme_truncated=True,
        changelog_text="changed",
        changelog_truncated=False,
        captured_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    store.save_project_docs(first)
    store.save_project_docs(second)
    assert store.get_project_docs("pg-repo-21") == second


# ---------------------------------------------------------------------------
# Spec 022 — discussion evidence store
# ---------------------------------------------------------------------------


def _make_discussion_evidence(
    discussion_id: str, number: int, **overrides: object
) -> DiscussionEvidence:
    kwargs: dict[str, object] = {
        "discussion_id": discussion_id,
        "discussion_url": f"https://github.com/owner/repo/discussions/{number}",
        "claim_type": "design_rationale",
        "summary": "summary text",
        "confidence": 0.8,
        "limitations": [],
        "source_inputs": [discussion_id],
        "generated_at": datetime(2026, 1, 1, tzinfo=UTC),
        "model": "test-model",
    }
    kwargs.update(overrides)
    return DiscussionEvidence(**kwargs)  # type: ignore[arg-type]


def test_postgres_discussion_evidence_store_returns_empty_when_absent(conninfo: str) -> None:
    store = PostgresDiscussionEvidenceStore(conninfo)
    assert store.get_discussion_evidence("pg-repo-19") == []


def test_postgres_discussion_evidence_store_roundtrips(conninfo: str) -> None:
    store = PostgresDiscussionEvidenceStore(conninfo)
    evidence = _make_discussion_evidence(
        "pg-d-1", 1, limitations=["low confidence"], source_inputs=["pg-d-1"]
    )

    store.save_discussion_evidence("pg-repo-20", [evidence])
    retrieved = store.get_discussion_evidence("pg-repo-20")

    assert retrieved == [evidence]


def test_postgres_discussion_evidence_store_upsert_overwrites(conninfo: str) -> None:
    store = PostgresDiscussionEvidenceStore(conninfo)
    store.save_discussion_evidence(
        "pg-repo-21", [_make_discussion_evidence("pg-d-2", 2, summary="first summary")]
    )

    store.save_discussion_evidence(
        "pg-repo-21",
        [_make_discussion_evidence("pg-d-2", 2, summary="second summary", confidence=0.9)],
    )

    result = store.get_discussion_evidence("pg-repo-21")
    assert len(result) == 1
    assert result[0].summary == "second summary"
    assert result[0].confidence == 0.9


# ---------------------------------------------------------------------------
# Spec 023 — embedding vector store
# ---------------------------------------------------------------------------


def _make_embedded_chunk(source_id: str, **overrides: object) -> EmbeddedChunk:
    kwargs: dict[str, object] = {
        "repository_id": "pg-repo-22",
        "source_type": "commit_analysis",
        "source_id": source_id,
        "text": "summary text",
        "vector": [0.1, 0.2, 0.3],
        "model": "text-embedding-3-small",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    kwargs.update(overrides)
    return EmbeddedChunk(**kwargs)  # type: ignore[arg-type]


def test_postgres_embedding_store_returns_empty_when_absent(conninfo: str) -> None:
    store = PostgresEmbeddingStore(conninfo)
    assert store.get_all_embeddings("pg-repo-22") == []


def test_postgres_embedding_store_roundtrips(conninfo: str) -> None:
    store = PostgresEmbeddingStore(conninfo)
    chunk = _make_embedded_chunk("pg-sha-1", repository_id="pg-repo-23")

    store.save_embeddings("pg-repo-23", [chunk])
    retrieved = store.get_all_embeddings("pg-repo-23")

    assert retrieved == [chunk]


def test_postgres_embedding_store_upsert_overwrites(conninfo: str) -> None:
    store = PostgresEmbeddingStore(conninfo)
    store.save_embeddings(
        "pg-repo-24",
        [_make_embedded_chunk("pg-sha-2", repository_id="pg-repo-24", text="first")],
    )

    store.save_embeddings(
        "pg-repo-24",
        [_make_embedded_chunk("pg-sha-2", repository_id="pg-repo-24", text="second")],
    )

    result = store.get_all_embeddings("pg-repo-24")
    assert len(result) == 1
    assert result[0].text == "second"


# ---------------------------------------------------------------------------
# Spec 026 — release evidence store
# ---------------------------------------------------------------------------


def _make_release_evidence(tag_name: str, **overrides: object) -> ReleaseEvidence:
    kwargs: dict[str, object] = {
        "tag_name": tag_name,
        "release_url": f"https://github.com/owner/repo/releases/tag/{tag_name}",
        "claim_type": "feature_release",
        "summary": "summary text",
        "confidence": 0.8,
        "limitations": [],
        "source_inputs": [tag_name],
        "generated_at": datetime(2026, 1, 1, tzinfo=UTC),
        "model": "test-model",
    }
    kwargs.update(overrides)
    return ReleaseEvidence(**kwargs)  # type: ignore[arg-type]


def test_postgres_release_evidence_store_returns_empty_when_absent(conninfo: str) -> None:
    store = PostgresReleaseEvidenceStore(conninfo)
    assert store.get_release_evidence("pg-repo-25") == []


def test_postgres_release_evidence_store_roundtrips(conninfo: str) -> None:
    store = PostgresReleaseEvidenceStore(conninfo)
    evidence = _make_release_evidence(
        "pg-v1.0.0", limitations=["low confidence"], source_inputs=["pg-v1.0.0"]
    )

    store.save_release_evidence("pg-repo-26", [evidence])
    retrieved = store.get_release_evidence("pg-repo-26")

    assert retrieved == [evidence]


def test_postgres_release_evidence_store_upsert_overwrites(conninfo: str) -> None:
    store = PostgresReleaseEvidenceStore(conninfo)
    store.save_release_evidence(
        "pg-repo-27", [_make_release_evidence("pg-v2.0.0", summary="first summary")]
    )

    store.save_release_evidence(
        "pg-repo-27",
        [_make_release_evidence("pg-v2.0.0", summary="second summary", confidence=0.9)],
    )

    result = store.get_release_evidence("pg-repo-27")
    assert len(result) == 1
    assert result[0].summary == "second summary"
    assert result[0].confidence == 0.9


# ---------------------------------------------------------------------------
# Spec 026 — advisory evidence store
# ---------------------------------------------------------------------------


def _make_advisory_evidence(ghsa_id: str, **overrides: object) -> AdvisoryEvidence:
    kwargs: dict[str, object] = {
        "ghsa_id": ghsa_id,
        "advisory_url": f"https://github.com/owner/repo/security/advisories/{ghsa_id}",
        "severity": "high",
        "summary": "summary text",
        "confidence": 0.8,
        "limitations": [],
        "source_inputs": [ghsa_id],
        "generated_at": datetime(2026, 1, 1, tzinfo=UTC),
        "model": "test-model",
    }
    kwargs.update(overrides)
    return AdvisoryEvidence(**kwargs)  # type: ignore[arg-type]


def test_postgres_advisory_evidence_store_returns_empty_when_absent(conninfo: str) -> None:
    store = PostgresAdvisoryEvidenceStore(conninfo)
    assert store.get_advisory_evidence("pg-repo-28") == []


def test_postgres_advisory_evidence_store_roundtrips(conninfo: str) -> None:
    store = PostgresAdvisoryEvidenceStore(conninfo)
    evidence = _make_advisory_evidence(
        "GHSA-pg01-0001-0001", limitations=["low confidence"], source_inputs=["GHSA-pg01-0001-0001"]
    )

    store.save_advisory_evidence("pg-repo-29", [evidence])
    retrieved = store.get_advisory_evidence("pg-repo-29")

    assert retrieved == [evidence]


def test_postgres_advisory_evidence_store_upsert_overwrites(conninfo: str) -> None:
    store = PostgresAdvisoryEvidenceStore(conninfo)
    store.save_advisory_evidence(
        "pg-repo-30", [_make_advisory_evidence("GHSA-pg02-0002-0002", summary="first summary")]
    )

    store.save_advisory_evidence(
        "pg-repo-30",
        [_make_advisory_evidence("GHSA-pg02-0002-0002", summary="second summary", confidence=0.9)],
    )

    result = store.get_advisory_evidence("pg-repo-30")
    assert len(result) == 1
    assert result[0].summary == "second summary"
    assert result[0].confidence == 0.9
