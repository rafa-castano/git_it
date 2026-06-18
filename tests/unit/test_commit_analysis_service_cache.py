from git_it.repository_ingestion.application.commit_analysis_service import CommitAnalysisService
from git_it.repository_ingestion.application.commit_query_service import CommitRecord
from git_it.repository_ingestion.application.ports import LLMMessage
from git_it.repository_ingestion.domain.analysis import (
    CommitAnalysis,
    CommitCategory,
    RiskLevel,
)
from tests.unit.fakes import FakeCommitReader


def _make_record(sha: str = "abc1234") -> CommitRecord:
    return CommitRecord(
        repository_id="repo-1",
        sha=sha,
        committed_at="2026-01-01T00:00:00+00:00",
        message="Some commit",
        author_name="Alice",
        committer_name="Alice",
        parent_shas=(),
    )


def _make_analysis(sha: str = "abc1234") -> CommitAnalysis:
    return CommitAnalysis(
        commit_sha=sha,
        summary="Cached",
        category=CommitCategory.CHORE,
        intent=None,
        intent_is_inferred=False,
        affected_components=[],
        risk_level=RiskLevel.LOW,
        confidence=0.9,
        evidence=[],
        limitations=[],
    )


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[LLMMessage]]] = []

    def analyze_commit(self, system: str, messages: list[LLMMessage]) -> CommitAnalysis:
        self.calls.append((system, list(messages)))
        return _make_analysis()


class FakeAnalysisStore:
    def __init__(self, cached: dict[str, CommitAnalysis] | None = None) -> None:
        self._cache: dict[str, CommitAnalysis] = cached or {}
        self.saved: list[tuple[CommitAnalysis, str]] = []

    def get_analysis(self, *, repository_id: str, commit_sha: str) -> CommitAnalysis | None:
        return self._cache.get(commit_sha)

    def save_analysis(self, analysis: CommitAnalysis, *, repository_id: str) -> bool:
        self.saved.append((analysis, repository_id))
        return True

    def list_analyses(
        self, repository_id: str, *, limit: int | None = None
    ) -> list[CommitAnalysis]:
        return list(self._cache.values())


def test_analyze_commits_skips_llm_when_analysis_cached() -> None:
    store = FakeAnalysisStore(cached={"sha1": _make_analysis("sha1")})
    client = FakeClient()
    service = CommitAnalysisService(
        reader=FakeCommitReader([_make_record("sha1")]),
        client=client,
        analysis_reader=store,
    )
    service.analyze_commits("repo-1")
    assert client.calls == []


def test_analyze_commits_saves_analysis_when_writer_provided() -> None:
    store = FakeAnalysisStore()
    client = FakeClient()
    service = CommitAnalysisService(
        reader=FakeCommitReader([_make_record("sha1")]),
        client=client,
        analysis_writer=store,
    )
    service.analyze_commits("repo-1")
    assert len(store.saved) == 1
    assert store.saved[0][1] == "repo-1"


def test_analyze_commits_does_not_save_when_cached() -> None:
    store = FakeAnalysisStore(cached={"sha1": _make_analysis("sha1")})
    client = FakeClient()
    service = CommitAnalysisService(
        reader=FakeCommitReader([_make_record("sha1")]),
        client=client,
        analysis_reader=store,
        analysis_writer=store,
    )
    service.analyze_commits("repo-1")
    assert store.saved == []
