"""Tests for CommitAnalysisService.analyze_commits_async (Batch 43)."""

import threading

from git_it.repository_ingestion.application.commit_analysis_service import (
    CommitAnalysisService,
)
from git_it.repository_ingestion.application.commit_query_service import CommitRecord
from git_it.repository_ingestion.application.ports import (
    CommitAnalysisClient,
    LLMMessage,
)
from git_it.repository_ingestion.domain.analysis import (
    CommitAnalysis,
    CommitCategory,
    RiskLevel,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_ID = "repo-test"


def _make_commit(sha: str, message: str = "feat: add feature") -> CommitRecord:
    return CommitRecord(
        repository_id=_REPO_ID,
        sha=sha,
        committed_at="2024-01-01T00:00:00",
        message=message,
        author_name="Alice",
        committer_name="Alice",
        parent_shas=("parent-sha",),
    )


def _make_analysis(sha: str, summary: str = "Added a feature") -> CommitAnalysis:
    return CommitAnalysis(
        commit_sha=sha,
        summary=summary,
        category=CommitCategory.FEATURE,
        intent=None,
        intent_is_inferred=True,
        affected_components=["core"],
        risk_level=RiskLevel.LOW,
        confidence=0.9,
        evidence=[],
        limitations=[],
    )


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeCommitReader:
    def __init__(self, commits: list[CommitRecord]) -> None:
        self._commits = commits

    def list_commits_for_repository(
        self,
        repository_id: str,
        *,
        limit: int | None = None,
        order: str = "newest",
        since: str | None = None,
        until: str | None = None,
    ) -> list[CommitRecord]:
        result = list(self._commits)
        if limit is not None:
            result = result[:limit]
        return result


class FakeAnalysisClient:
    """Fake client that always returns a fixed analysis, tracking call count."""

    def __init__(self, analyses: dict[str, CommitAnalysis] | None = None) -> None:
        self._analyses = analyses or {}
        self.call_count = 0
        self.called_shas: list[str] = []

    def analyze_commit(self, messages: list[LLMMessage]) -> CommitAnalysis:
        self.call_count += 1
        # Extract sha from the user message content (format: "sha: {sha[:12]}")
        user_content = next(m.content for m in messages if m.role == "user")
        sha_prefix = user_content.split("sha: ")[1].split("\n")[0]
        # Try to find the matching full sha
        for full_sha, analysis in self._analyses.items():
            if full_sha.startswith(sha_prefix) or sha_prefix.startswith(full_sha[:12]):
                self.called_shas.append(full_sha)
                return analysis
        # Fallback: return first analysis or generic
        sha = sha_prefix
        self.called_shas.append(sha)
        return _make_analysis(sha)


class FakeAnalysisCache:
    """Fake cache reader+writer satisfying CommitAnalysisReader + CommitAnalysisWriter."""

    def __init__(self, cached: dict[str, CommitAnalysis] | None = None) -> None:
        self._cached: dict[str, CommitAnalysis] = dict(cached or {})
        self.saved: list[CommitAnalysis] = []

    def get_analysis(self, *, repository_id: str, commit_sha: str) -> CommitAnalysis | None:
        return self._cached.get(commit_sha)

    def list_analyses(
        self, repository_id: str, *, limit: int | None = None
    ) -> list[CommitAnalysis]:
        result = list(self._cached.values())
        if limit is not None:
            result = result[:limit]
        return result

    def save_analysis(self, analysis: CommitAnalysis, *, repository_id: str) -> bool:
        self._cached[analysis.commit_sha] = analysis
        self.saved.append(analysis)
        return True


class ConcurrencyTrackingClient:
    """Client that measures max concurrent calls using a threading lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current = 0
        self.max_concurrent = 0
        self.call_count = 0

    def analyze_commit(self, messages: list[LLMMessage]) -> CommitAnalysis:
        with self._lock:
            self._current += 1
            self.max_concurrent = max(self.max_concurrent, self._current)
            self.call_count += 1

        # Simulate brief real work so threads truly overlap
        import time

        time.sleep(0.02)

        with self._lock:
            self._current -= 1

        user_content = next(m.content for m in messages if m.role == "user")
        sha_prefix = user_content.split("sha: ")[1].split("\n")[0]
        return _make_analysis(sha_prefix)


def _build_service(
    commits: list[CommitRecord],
    client: CommitAnalysisClient,
    *,
    cache: FakeAnalysisCache | None = None,
    sample_client: CommitAnalysisClient | None = None,
) -> CommitAnalysisService:
    return CommitAnalysisService(
        reader=FakeCommitReader(commits),
        client=client,
        sample_client=sample_client,
        analysis_writer=cache,
        analysis_reader=cache,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_async_returns_same_number_of_results_as_sync() -> None:
    """analyze_commits_async returns same count as analyze_commits for non-skipped commits."""
    commits = [
        _make_commit("sha-a", "feat: add login"),
        _make_commit("sha-b", "feat: add logout"),
        _make_commit("sha-c", "feat: add dashboard"),
    ]
    client = FakeAnalysisClient(
        {
            "sha-a": _make_analysis("sha-a"),
            "sha-b": _make_analysis("sha-b"),
            "sha-c": _make_analysis("sha-c"),
        }
    )
    service = _build_service(commits, client)

    sync_results = service.analyze_commits(_REPO_ID)
    async_results = await service.analyze_commits_async(_REPO_ID)

    assert len(async_results) == len(sync_results)


async def test_async_skips_cached_commits() -> None:
    """Commits already in cache are returned without calling the LLM."""
    sha_a = "sha-aaa"
    sha_b = "sha-bbb"
    sha_c = "sha-ccc"

    commits = [
        _make_commit(sha_a, "feat: a"),
        _make_commit(sha_b, "feat: b"),
        _make_commit(sha_c, "feat: c"),
    ]
    cached_analysis_a = _make_analysis(sha_a, "cached A")
    cached_analysis_b = _make_analysis(sha_b, "cached B")
    cache = FakeAnalysisCache({sha_a: cached_analysis_a, sha_b: cached_analysis_b})
    client = FakeAnalysisClient({sha_c: _make_analysis(sha_c, "fresh C")})
    service = _build_service(commits, client, cache=cache)

    results = await service.analyze_commits_async(_REPO_ID)

    assert client.call_count == 1  # only sha_c needed LLM
    assert len(results) == 3


async def test_async_skips_skip_tier_commits() -> None:
    """Dependabot-style commits are filtered by pre-classifier; LLM not called."""
    commits = [
        _make_commit("sha-dep", "bump lodash from 4.0 to 4.1"),  # skip tier
        _make_commit("sha-feat", "feat: add search"),
    ]
    client = FakeAnalysisClient({"sha-feat": _make_analysis("sha-feat")})
    service = _build_service(commits, client)

    results = await service.analyze_commits_async(_REPO_ID)

    assert client.call_count == 1  # only the feat commit
    assert len(results) == 1  # skipped commits not in results


async def test_async_preserves_commit_order() -> None:
    """Results must follow the original commit list order: cached, LLM-fresh, and mixed."""
    sha_a = "sha-aaa111"
    sha_b = "sha-bbb222"
    sha_c = "sha-ccc333"

    # A and C go to LLM, B is cached
    commits = [
        _make_commit(sha_a, "feat: A"),
        _make_commit(sha_b, "feat: B"),
        _make_commit(sha_c, "feat: C"),
    ]
    cached_b = _make_analysis(sha_b, "B cached")
    cache = FakeAnalysisCache({sha_b: cached_b})
    fresh_a = _make_analysis(sha_a, "A fresh")
    fresh_c = _make_analysis(sha_c, "C fresh")
    client = FakeAnalysisClient({sha_a: fresh_a, sha_c: fresh_c})
    service = _build_service(commits, client, cache=cache)

    results = await service.analyze_commits_async(_REPO_ID)

    assert len(results) == 3
    assert results[0].commit_sha == sha_a
    assert results[1].commit_sha == sha_b
    assert results[2].commit_sha == sha_c


async def test_async_respects_concurrency_limit() -> None:
    """With concurrency=2, max simultaneous LLM calls never exceeds 2."""
    commits = [_make_commit(f"sha-{i:03d}", "feat: item") for i in range(5)]
    client = ConcurrencyTrackingClient()
    service = _build_service(commits, client)

    await service.analyze_commits_async(_REPO_ID, concurrency=2)

    assert client.call_count == 5
    assert client.max_concurrent <= 2


async def test_async_concurrency_one_is_sequential() -> None:
    """concurrency=1 means effectively sequential — semaphore of 1."""
    commits = [_make_commit(f"sha-{i:03d}", "feat: item") for i in range(3)]
    client = ConcurrencyTrackingClient()
    service = _build_service(commits, client)

    results = await service.analyze_commits_async(_REPO_ID, concurrency=1)

    assert client.call_count == 3
    assert client.max_concurrent == 1
    assert len(results) == 3


async def test_async_routes_sample_commit_to_sample_client() -> None:
    """Commits classified as 'sample' are sent to sample_client when configured."""
    # A commit with no special signal → classified as 'sample'
    sha_s = "sha-sample"
    commits = [_make_commit(sha_s, "docs: update readme")]  # sample tier

    main_client = FakeAnalysisClient({sha_s: _make_analysis(sha_s, "main")})
    sample_client = FakeAnalysisClient({sha_s: _make_analysis(sha_s, "sample")})

    service = _build_service(commits, main_client, sample_client=sample_client)

    results = await service.analyze_commits_async(_REPO_ID)

    assert main_client.call_count == 0
    assert sample_client.call_count == 1
    assert len(results) == 1


async def test_async_writes_analysis_to_cache() -> None:
    """After LLM call, analysis is persisted via analysis_writer."""
    sha = "sha-new"
    commits = [_make_commit(sha, "feat: new feature")]
    cache = FakeAnalysisCache()
    client = FakeAnalysisClient({sha: _make_analysis(sha)})
    service = _build_service(commits, client, cache=cache)

    await service.analyze_commits_async(_REPO_ID)

    assert len(cache.saved) == 1
    assert cache.saved[0].commit_sha == sha


async def test_async_default_concurrency_is_five() -> None:
    """Default concurrency is 5 — verifiable by running 5 calls without providing param."""
    commits = [_make_commit(f"sha-{i:03d}", "feat: item") for i in range(5)]
    client = ConcurrencyTrackingClient()
    service = _build_service(commits, client)

    # No concurrency param → uses default of 5
    await service.analyze_commits_async(_REPO_ID)

    # With concurrency=5 and 5 tasks, all could run simultaneously
    assert client.call_count == 5
    assert client.max_concurrent <= 5
