"""Tests for CommitAnalysisService.estimate_llm_calls()."""

from git_it.repository_ingestion.application.commit_analysis_service import CommitAnalysisService
from git_it.repository_ingestion.application.commit_query_service import CommitRecord
from git_it.repository_ingestion.application.ports import LLMMessage
from git_it.repository_ingestion.domain.analysis import (
    CommitAnalysis,
    CommitCategory,
    RiskLevel,
)

# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------


def _make_record(
    sha: str = "abc1234",
    message: str = "feat: add feature",
    author: str = "Alice",
    parent_shas: tuple[str, ...] = (),
) -> CommitRecord:
    return CommitRecord(
        repository_id="repo-1",
        sha=sha,
        committed_at="2026-01-01T00:00:00+00:00",
        message=message,
        author_name=author,
        committer_name=author,
        parent_shas=parent_shas,
    )


def _make_analysis(sha: str = "abc1234") -> CommitAnalysis:
    return CommitAnalysis(
        commit_sha=sha,
        summary="Added a feature",
        category=CommitCategory.FEATURE,
        intent=None,
        intent_is_inferred=True,
        affected_components=["core"],
        risk_level=RiskLevel.LOW,
        confidence=0.7,
        evidence=[],
        limitations=[],
    )


class FakeCommitAnalysisClient:
    def __init__(self, response: CommitAnalysis | None = None) -> None:
        self._response = response or _make_analysis()
        self.calls: list[tuple[str, list[LLMMessage]]] = []

    def analyze_commit(self, system: str, messages: list[LLMMessage]) -> CommitAnalysis:
        self.calls.append((system, list(messages)))
        return self._response


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


class FakeCacheReader:
    """Simulates a CommitAnalysisReader with a fixed set of cached SHAs."""

    def __init__(self, cached_shas: set[str] | None = None) -> None:
        self._cached: set[str] = cached_shas or set()
        self.get_analysis_calls: list[str] = []
        self.list_analyses_calls: int = 0

    def get_analysis(self, *, repository_id: str, commit_sha: str) -> CommitAnalysis | None:
        self.get_analysis_calls.append(commit_sha)
        if commit_sha in self._cached:
            return _make_analysis(sha=commit_sha)
        return None

    def list_analyses(
        self, repository_id: str, *, limit: int | None = None
    ) -> list[CommitAnalysis]:
        self.list_analyses_calls += 1
        analyses = [_make_analysis(sha=sha) for sha in sorted(self._cached)]
        return analyses[:limit] if limit is not None else analyses


def _make_service(
    records: list[CommitRecord] | None = None,
    cache_reader: FakeCacheReader | None = None,
) -> CommitAnalysisService:
    reader = FakeCommitReader(records)
    client = FakeCommitAnalysisClient()
    return CommitAnalysisService(
        reader=reader,
        client=client,
        analysis_reader=cache_reader,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_returns_zero_when_no_commits() -> None:
    service = _make_service(records=[])
    assert service.estimate_llm_calls("repo-1") == 0


def test_returns_zero_when_all_cached() -> None:
    records = [_make_record("sha1"), _make_record("sha2")]
    cache = FakeCacheReader(cached_shas={"sha1", "sha2"})
    service = _make_service(records=records, cache_reader=cache)
    assert service.estimate_llm_calls("repo-1") == 0


def test_returns_zero_when_all_skipped_by_classifier() -> None:
    records = [
        _make_record("sha1", message="Bump lodash from 4.17.20 to 4.17.21"),
        _make_record("sha2", message="Bump axios from 1.0.0 to 1.1.0"),
    ]
    service = _make_service(records=records)
    assert service.estimate_llm_calls("repo-1") == 0


def test_counts_uncached_unskipped_commits() -> None:
    # sha1: cached → skip (cache hit)
    # sha2: dependabot bump → skip (pre-classifier)
    # sha3, sha4: normal → counted
    records = [
        _make_record("sha1", message="feat: auth"),
        _make_record("sha2", message="Bump lodash from 4.17.20 to 4.17.21"),
        _make_record("sha3", message="feat: add dashboard"),
        _make_record("sha4", message="fix: null pointer in login"),
    ]
    cache = FakeCacheReader(cached_shas={"sha1"})
    service = _make_service(records=records, cache_reader=cache)
    assert service.estimate_llm_calls("repo-1") == 2


def test_estimate_uses_bulk_cache_lookup_instead_of_per_commit_lookup() -> None:
    records = [_make_record(f"sha{i}", message=f"feat: feature {i}") for i in range(100)]
    cache = FakeCacheReader(cached_shas={"sha0", "sha2", "sha4"})
    service = _make_service(records=records, cache_reader=cache)

    assert service.estimate_llm_calls("repo-1") == 97
    assert cache.list_analyses_calls == 1
    assert cache.get_analysis_calls == []


def test_respects_limit_parameter() -> None:
    records = [_make_record(f"sha{i}", message=f"feat: feature {i}") for i in range(10)]
    service = _make_service(records=records)
    assert service.estimate_llm_calls("repo-1", limit=3) == 3


def test_include_commits_are_counted() -> None:
    records = [_make_record("sha1", message="feat: add auth")]
    service = _make_service(records=records)
    assert service.estimate_llm_calls("repo-1") == 1


def test_sample_commits_are_counted() -> None:
    records = [_make_record("sha1", message="Add logging to request handler")]
    service = _make_service(records=records)
    assert service.estimate_llm_calls("repo-1") == 1


def test_no_cache_reader_counts_all_unskipped() -> None:
    records = [
        _make_record("sha1", message="feat: add login"),
        _make_record("sha2", message="Bump lodash from 4.17.20 to 4.17.21"),
        _make_record("sha3", message="Add logging"),
    ]
    # analysis_reader=None → no cache check
    reader = FakeCommitReader(records)
    client = FakeCommitAnalysisClient()
    service = CommitAnalysisService(reader=reader, client=client, analysis_reader=None)
    assert service.estimate_llm_calls("repo-1") == 2
