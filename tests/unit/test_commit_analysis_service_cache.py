from dataclasses import replace

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
        summary_beginner="",
        summary_expert="",
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


# ── AC-3: re-analysis trigger based on summary_beginner sentinel ─────────────


def _make_legacy_analysis(sha: str = "sha1") -> CommitAnalysis:
    """Pre-feature analysis: summary_beginner is None (default)."""
    return CommitAnalysis(
        commit_sha=sha,
        summary="Legacy summary",
        category=CommitCategory.CHORE,
        confidence=0.8,
        evidence=[],
        limitations=[],
    )


def _make_dual_analysis(sha: str = "sha1") -> CommitAnalysis:
    """Post-feature analysis: summary_beginner is not None (even if empty string)."""
    return CommitAnalysis(
        commit_sha=sha,
        summary="Expert summary",
        summary_beginner="Plain explanation",
        summary_expert="Terse technical note",
        category=CommitCategory.CHORE,
        confidence=0.8,
        evidence=[],
        limitations=[],
    )


def _make_self_explanatory_analysis(sha: str = "sha1") -> CommitAnalysis:
    """Post-feature analysis where LLM deemed message self-explanatory: empty strings."""
    return CommitAnalysis(
        commit_sha=sha,
        summary="Fix typo",
        summary_beginner="",
        summary_expert="",
        category=CommitCategory.CHORE,
        confidence=0.9,
        evidence=[],
        limitations=[],
    )


def test_legacy_analysis_without_dual_summary_triggers_reanalysis() -> None:
    legacy = _make_legacy_analysis("sha1")
    assert legacy.summary_beginner is None
    store = FakeAnalysisStore(cached={"sha1": legacy})
    client = FakeClient()
    service = CommitAnalysisService(
        reader=FakeCommitReader([_make_record("sha1")]),
        client=client,
        analysis_reader=store,
        analysis_writer=store,
    )
    service.analyze_commits("repo-1")
    assert len(client.calls) == 1, "Legacy analysis should trigger re-analysis"


def test_dual_analysis_with_non_none_beginner_is_skipped() -> None:
    dual = _make_dual_analysis("sha1")
    assert dual.summary_beginner is not None
    store = FakeAnalysisStore(cached={"sha1": dual})
    client = FakeClient()
    service = CommitAnalysisService(
        reader=FakeCommitReader([_make_record("sha1")]),
        client=client,
        analysis_reader=store,
    )
    service.analyze_commits("repo-1")
    assert client.calls == [], "Up-to-date dual-summary analysis should be skipped"


def test_self_explanatory_analysis_with_empty_string_is_skipped() -> None:
    self_exp = _make_self_explanatory_analysis("sha1")
    assert self_exp.summary_beginner == ""
    store = FakeAnalysisStore(cached={"sha1": self_exp})
    client = FakeClient()
    service = CommitAnalysisService(
        reader=FakeCommitReader([_make_record("sha1")]),
        client=client,
        analysis_reader=store,
    )
    service.analyze_commits("repo-1")
    assert client.calls == [], (
        "Empty-string summary_beginner means 'analyzed, no text needed' — skip"
    )


def test_progress_total_with_max_new_counts_only_planned_new_analyses() -> None:
    store = FakeAnalysisStore(cached={"cached": _make_dual_analysis("cached")})
    client = FakeClient()
    progress: list[tuple[int, int]] = []
    skipped = replace(
        _make_record("skipped"),
        message="Bump lodash from 4.17.20 to 4.17.21",
    )
    service = CommitAnalysisService(
        reader=FakeCommitReader(
            [
                _make_record("cached"),
                skipped,
                _make_record("new-1"),
                _make_record("new-2"),
            ]
        ),
        client=client,
        analysis_reader=store,
    )

    service.analyze_commits(
        "repo-1",
        max_new=9999,
        on_progress=lambda done, total: progress.append((done, total)),
    )

    assert len(client.calls) == 2
    assert progress == [(1, 2), (2, 2)]
