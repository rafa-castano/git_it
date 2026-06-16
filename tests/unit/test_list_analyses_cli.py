from pathlib import Path

import pytest

from git_it.repository_ingestion.domain.analysis import (
    CommitAnalysis,
    CommitCategory,
    RiskLevel,
)
from git_it.repository_ingestion.interfaces.cli import main


def _make_analysis(sha: str = "abc1234", summary: str = "Added feature") -> CommitAnalysis:
    return CommitAnalysis(
        commit_sha=sha,
        summary=summary,
        category=CommitCategory.FEATURE,
        intent=None,
        intent_is_inferred=False,
        affected_components=["core"],
        risk_level=RiskLevel.LOW,
        confidence=0.9,
        evidence=[],
        limitations=[],
    )


class FakeAnalysisStore:
    def __init__(self, analyses: list[CommitAnalysis] | None = None) -> None:
        self._analyses = analyses or []

    def list_analyses(
        self, repository_id: str, *, limit: int | None = None
    ) -> list[CommitAnalysis]:
        data = list(self._analyses)
        if limit is not None:
            data = data[:limit]
        return data

    def get_analysis(self, *, repository_id: str, commit_sha: str) -> CommitAnalysis | None:
        return None


def _factory(store: FakeAnalysisStore):  # type: ignore[no-untyped-def]
    def factory(*, project_root: Path, repository_id: str) -> FakeAnalysisStore:
        return store

    return factory


def test_list_analyses_exits_zero(tmp_path: Path) -> None:
    code = main(
        ["list-analyses", "https://github.com/owner/repo"],
        project_root=tmp_path,
        list_analyses_factory=_factory(FakeAnalysisStore()),
    )
    assert code == 0


def test_list_analyses_shows_no_data_message_when_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(
        ["list-analyses", "https://github.com/owner/repo"],
        project_root=tmp_path,
        list_analyses_factory=_factory(FakeAnalysisStore()),
    )
    captured = capsys.readouterr()
    assert "No" in captured.out


def test_list_analyses_prints_stored_analyses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = FakeAnalysisStore([_make_analysis("deadbeef", "Implement login")])
    main(
        ["list-analyses", "https://github.com/owner/repo"],
        project_root=tmp_path,
        list_analyses_factory=_factory(store),
    )
    captured = capsys.readouterr()
    assert "deadbee" in captured.out
    assert "Implement login" in captured.out


def test_list_analyses_respects_limit_flag(tmp_path: Path) -> None:
    store = FakeAnalysisStore([_make_analysis(f"sha{i}") for i in range(5)])
    received: list[int | None] = []

    def factory(*, project_root: Path, repository_id: str) -> FakeAnalysisStore:
        class LimitCapture:
            def list_analyses(
                self, repo_id: str, *, limit: int | None = None
            ) -> list[CommitAnalysis]:
                received.append(limit)
                return store.list_analyses(repo_id, limit=limit)

            def get_analysis(self, *, repository_id: str, commit_sha: str) -> CommitAnalysis | None:
                return None

        return LimitCapture()  # type: ignore[return-value]

    main(
        ["list-analyses", "https://github.com/owner/repo", "--limit", "3"],
        project_root=tmp_path,
        list_analyses_factory=factory,
    )
    assert received == [3]
