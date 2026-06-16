"""Tests for tiered model routing: include-tier → primary client, sample-tier → sample_client."""

from git_it.repository_ingestion.application.commit_analysis_service import CommitAnalysisService
from git_it.repository_ingestion.application.commit_query_service import CommitRecord
from git_it.repository_ingestion.application.ports import LLMMessage
from git_it.repository_ingestion.domain.analysis import (
    CommitAnalysis,
    CommitCategory,
    RiskLevel,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    sha: str = "abc1234",
    message: str = "feat: add auth",
    author: str = "Alice",
) -> CommitRecord:
    return CommitRecord(
        repository_id="repo-1",
        sha=sha,
        committed_at="2026-01-01T00:00:00+00:00",
        message=message,
        author_name=author,
        committer_name=author,
        parent_shas=(),
    )


def _make_analysis(sha: str = "abc1234") -> CommitAnalysis:
    return CommitAnalysis(
        commit_sha=sha,
        summary="Analysis result",
        category=CommitCategory.FEATURE,
        intent=None,
        intent_is_inferred=True,
        affected_components=["core"],
        risk_level=RiskLevel.LOW,
        confidence=0.8,
        evidence=[],
        limitations=[],
    )


class RecordingClient:
    """Fake LLM client that records which commit SHAs it analyzed."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.analyzed_shas: list[str] = []

    def analyze_commit(self, messages: list[LLMMessage]) -> CommitAnalysis:
        sha = "unknown"
        for m in messages:
            if "[REPOSITORY DATA]" in m.content:
                for line in m.content.splitlines():
                    if line.startswith("sha:"):
                        sha = line.split(":", 1)[1].strip()
                        break
        self.analyzed_shas.append(sha)
        return _make_analysis(sha)


class FakeCommitReader:
    def __init__(self, records: list[CommitRecord] | None = None) -> None:
        self._records = records or []

    def list_commits_for_repository(
        self,
        repository_id: str,
        *,
        limit: int | None = None,
        order: str = "newest",
        since: str | None = None,
        until: str | None = None,
    ) -> list[CommitRecord]:
        return self._records[:limit] if limit is not None else list(self._records)


def _make_service(
    records: list[CommitRecord] | None = None,
    primary: RecordingClient | None = None,
    sample: RecordingClient | None = None,
) -> tuple[CommitAnalysisService, RecordingClient, RecordingClient | None]:
    primary = primary or RecordingClient("primary")
    reader = FakeCommitReader(records)
    service = CommitAnalysisService(
        reader=reader,
        client=primary,
        sample_client=sample,
    )
    return service, primary, sample


# ---------------------------------------------------------------------------
# Tests: tiered routing in analyze_commits()
# ---------------------------------------------------------------------------


def test_include_commit_uses_primary_client() -> None:
    """feat: commit (include tier) must go to the primary client only."""
    primary = RecordingClient("primary")
    sample = RecordingClient("sample")
    records = [_make_record(sha="aaa111", message="feat: add auth")]
    service, _, _ = _make_service(records=records, primary=primary, sample=sample)

    service.analyze_commits("repo-1")

    assert "aaa111" in primary.analyzed_shas
    assert sample.analyzed_shas == []


def test_sample_commit_uses_sample_client_when_configured() -> None:
    """Non-conventional commit (sample tier) must go to sample_client when it is set."""
    primary = RecordingClient("primary")
    sample = RecordingClient("sample")
    records = [_make_record(sha="bbb222", message="Add logging to request handler")]
    service, _, _ = _make_service(records=records, primary=primary, sample=sample)

    service.analyze_commits("repo-1")

    assert "bbb222" in sample.analyzed_shas
    assert primary.analyzed_shas == []


def test_sample_commit_uses_primary_client_when_no_sample_client() -> None:
    """When sample_client is None, sample-tier commits fall back to the primary client."""
    primary = RecordingClient("primary")
    records = [_make_record(sha="ccc333", message="Add logging to request handler")]
    service, _, _ = _make_service(records=records, primary=primary, sample=None)

    service.analyze_commits("repo-1")

    assert "ccc333" in primary.analyzed_shas


def test_analyze_commit_public_method_always_uses_primary_client() -> None:
    """analyze_commit() (single-commit public API) always uses the primary client."""
    primary = RecordingClient("primary")
    sample = RecordingClient("sample")
    # sample-tier message — but public method bypasses pre-classifier
    commit = _make_record(sha="ddd444", message="Add logging to request handler")
    reader = FakeCommitReader()
    service = CommitAnalysisService(
        reader=reader,
        client=primary,
        sample_client=sample,
    )

    service.analyze_commit(commit, repo_context=None)

    assert "ddd444" in primary.analyzed_shas
    assert sample.analyzed_shas == []


def test_mixed_batch_routes_correctly() -> None:
    """3 commits: feat (include), plain (sample), Bump (skip) → primary=1, sample=1, total=2."""
    primary = RecordingClient("primary")
    sample = RecordingClient("sample")
    records = [
        _make_record(sha="feat11", message="feat: new feature"),
        _make_record(sha="samp22", message="Add logging"),
        _make_record(sha="skip33", message="Bump lodash from 4.17.20 to 4.17.21"),
    ]
    service, _, _ = _make_service(records=records, primary=primary, sample=sample)

    results = service.analyze_commits("repo-1")

    assert len(results) == 2
    assert primary.analyzed_shas == ["feat11"]
    assert sample.analyzed_shas == ["samp22"]


def test_skip_commits_use_neither_client() -> None:
    """Commits that are skipped must not call either client."""
    primary = RecordingClient("primary")
    sample = RecordingClient("sample")
    records = [
        _make_record(sha="dep111", message="Bump lodash from 4.17.20 to 4.17.21"),
        _make_record(sha="dep222", message="chore(deps): update axios to 1.6.0"),
    ]
    service, _, _ = _make_service(records=records, primary=primary, sample=sample)

    results = service.analyze_commits("repo-1")

    assert results == []
    assert primary.analyzed_shas == []
    assert sample.analyzed_shas == []
