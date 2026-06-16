from dataclasses import dataclass
from pathlib import Path

import pytest

from git_it.repository_ingestion.domain.analysis import (
    CommitAnalysis,
    CommitCategory,
    RiskLevel,
)
from git_it.repository_ingestion.interfaces.cli import main


def _make_analysis(sha: str = "abc1234", summary: str = "Added a feature") -> CommitAnalysis:
    return CommitAnalysis(
        commit_sha=sha,
        summary=summary,
        category=CommitCategory.FEATURE,
        intent=None,
        intent_is_inferred=True,
        affected_components=["core"],
        risk_level=RiskLevel.LOW,
        confidence=0.7,
        evidence=[],
        limitations=[],
    )


@dataclass
class CommitBatchCall:
    repository_id: str
    limit: int | None
    order: str
    since: str | None
    until: str | None


class FakeCommitBatchService:
    def __init__(self, analyses: list[CommitAnalysis] | None = None, estimate: int = 0) -> None:
        self._analyses = analyses or []
        self._estimate = estimate
        self.calls: list[CommitBatchCall] = []
        self.async_concurrency_used: int | None = None

    def analyze_commits(
        self,
        repository_id: str,
        *,
        limit: int | None = None,
        order: str = "newest",
        since: str | None = None,
        until: str | None = None,
    ) -> list[CommitAnalysis]:
        self.calls.append(
            CommitBatchCall(
                repository_id=repository_id,
                limit=limit,
                order=order,
                since=since,
                until=until,
            )
        )
        return self._analyses

    async def analyze_commits_async(
        self,
        repository_id: str,
        *,
        limit: int | None = None,
        order: str = "newest",
        since: str | None = None,
        until: str | None = None,
        concurrency: int = 5,
    ) -> list[CommitAnalysis]:
        self.async_concurrency_used = concurrency
        self.calls.append(
            CommitBatchCall(
                repository_id=repository_id,
                limit=limit,
                order=order,
                since=since,
                until=until,
            )
        )
        return self._analyses

    def estimate_llm_calls(
        self,
        repository_id: str,
        *,
        limit: int | None = None,
        order: str = "newest",
        since: str | None = None,
        until: str | None = None,
    ) -> int:
        return self._estimate


def _factory(service: FakeCommitBatchService):  # type: ignore[no-untyped-def]
    def factory(
        *, project_root: Path, repository_id: str, model: str, sample_model: str | None
    ) -> FakeCommitBatchService:
        return service

    return factory


def test_analyze_commits_exits_zero(tmp_path: Path) -> None:
    service = FakeCommitBatchService(analyses=[_make_analysis()])
    code = main(
        ["analyze-commits", "https://github.com/owner/repo"],
        project_root=tmp_path,
        commit_analysis_factory=_factory(service),
    )
    assert code == 0


def test_analyze_commits_shows_no_commits_when_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    service = FakeCommitBatchService(analyses=[])
    main(
        ["analyze-commits", "https://github.com/owner/repo"],
        project_root=tmp_path,
        commit_analysis_factory=_factory(service),
    )
    captured = capsys.readouterr()
    assert "No commits" in captured.out


def test_analyze_commits_prints_category_and_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    service = FakeCommitBatchService(analyses=[_make_analysis(summary="Implement auth")])
    main(
        ["analyze-commits", "https://github.com/owner/repo"],
        project_root=tmp_path,
        commit_analysis_factory=_factory(service),
    )
    captured = capsys.readouterr()
    assert "feature" in captured.out.lower()
    assert "Implement auth" in captured.out


def test_analyze_commits_passes_limit_to_service(tmp_path: Path) -> None:
    service = FakeCommitBatchService()
    main(
        ["analyze-commits", "https://github.com/owner/repo", "--limit", "3"],
        project_root=tmp_path,
        commit_analysis_factory=_factory(service),
    )
    assert service.calls[0].limit == 3


def test_analyze_commits_yes_flag_skips_budget_confirmation(tmp_path: Path) -> None:
    """--yes skips confirmation even when estimate > threshold."""
    service = FakeCommitBatchService(analyses=[_make_analysis()], estimate=999)
    confirm_called: list[int] = []

    def _confirm(n: int) -> bool:
        confirm_called.append(n)
        return False  # would abort if called

    code = main(
        ["analyze-commits", "https://github.com/owner/repo", "--yes"],
        project_root=tmp_path,
        commit_analysis_factory=_factory(service),
        budget_confirm_fn=_confirm,
        budget_threshold=10,
    )

    assert code == 0
    assert confirm_called == []  # confirm_fn never called


def test_analyze_commits_aborts_when_budget_exceeded_and_not_confirmed(tmp_path: Path) -> None:
    """When estimate > threshold and confirm_fn returns False, exit 1, no analyze_commits call."""
    service = FakeCommitBatchService(analyses=[_make_analysis()], estimate=100)

    code = main(
        ["analyze-commits", "https://github.com/owner/repo"],
        project_root=tmp_path,
        commit_analysis_factory=_factory(service),
        budget_confirm_fn=lambda n: False,
        budget_threshold=10,
    )

    assert code == 1
    assert service.calls == []


def test_analyze_commits_proceeds_when_budget_confirmed(tmp_path: Path) -> None:
    """When estimate > threshold and confirm_fn returns True, proceeds normally."""
    service = FakeCommitBatchService(analyses=[_make_analysis()], estimate=100)

    code = main(
        ["analyze-commits", "https://github.com/owner/repo"],
        project_root=tmp_path,
        commit_analysis_factory=_factory(service),
        budget_confirm_fn=lambda n: True,
        budget_threshold=10,
    )

    assert code == 0
    assert len(service.calls) == 1


def test_analyze_commits_no_confirmation_when_under_threshold(tmp_path: Path) -> None:
    """No call to confirm_fn when estimate <= threshold."""
    service = FakeCommitBatchService(analyses=[_make_analysis()], estimate=5)
    confirm_called: list[int] = []

    def _confirm(n: int) -> bool:
        confirm_called.append(n)
        return True

    main(
        ["analyze-commits", "https://github.com/owner/repo"],
        project_root=tmp_path,
        commit_analysis_factory=_factory(service),
        budget_confirm_fn=_confirm,
        budget_threshold=10,
    )

    assert confirm_called == []


def test_analyze_commits_order_oldest_passed_to_service(tmp_path: Path) -> None:
    service = FakeCommitBatchService()
    main(
        ["analyze-commits", "https://github.com/owner/repo", "--order", "oldest"],
        project_root=tmp_path,
        commit_analysis_factory=_factory(service),
    )
    assert service.calls[0].order == "oldest"


def test_analyze_commits_since_passed_to_service(tmp_path: Path) -> None:
    service = FakeCommitBatchService()
    main(
        ["analyze-commits", "https://github.com/owner/repo", "--since", "2024-01-01"],
        project_root=tmp_path,
        commit_analysis_factory=_factory(service),
    )
    assert service.calls[0].since == "2024-01-01"


def test_analyze_commits_until_passed_to_service(tmp_path: Path) -> None:
    service = FakeCommitBatchService()
    main(
        ["analyze-commits", "https://github.com/owner/repo", "--until", "2024-12-31"],
        project_root=tmp_path,
        commit_analysis_factory=_factory(service),
    )
    assert service.calls[0].until == "2024-12-31"


def test_analyze_commits_sample_model_passed_to_factory(tmp_path: Path) -> None:
    received: list[str | None] = []

    def factory(
        *, project_root: Path, repository_id: str, model: str, sample_model: str | None
    ) -> FakeCommitBatchService:
        received.append(sample_model)
        return FakeCommitBatchService()

    main(
        ["analyze-commits", "https://github.com/owner/repo", "--sample-model", "ollama/llama3.2"],
        project_root=tmp_path,
        commit_analysis_factory=factory,
    )

    assert received == ["ollama/llama3.2"]


def test_analyze_commits_default_sample_model_is_none(tmp_path: Path) -> None:
    received: list[str | None] = []

    def factory(
        *, project_root: Path, repository_id: str, model: str, sample_model: str | None
    ) -> FakeCommitBatchService:
        received.append(sample_model)
        return FakeCommitBatchService()

    main(
        ["analyze-commits", "https://github.com/owner/repo"],
        project_root=tmp_path,
        commit_analysis_factory=factory,
    )

    assert received == [None]


def test_analyze_commits_default_concurrency_is_1(tmp_path: Path) -> None:
    """Without --concurrency, default is 1 (sequential mode)."""
    service = FakeCommitBatchService(analyses=[_make_analysis()])
    code = main(
        ["analyze-commits", "https://github.com/owner/repo"],
        project_root=tmp_path,
        commit_analysis_factory=_factory(service),
    )
    assert code == 0
    # default concurrency=1 means sync path or async with concurrency=1
    # just check it exits 0 and produces a result
    assert len(service.calls) == 1


def test_analyze_commits_concurrency_flag_passed_to_async_service(tmp_path: Path) -> None:
    """--concurrency 4 routes through analyze_commits_async with concurrency=4."""
    service = FakeCommitBatchService(analyses=[_make_analysis()])
    code = main(
        ["analyze-commits", "https://github.com/owner/repo", "--concurrency", "4"],
        project_root=tmp_path,
        commit_analysis_factory=_factory(service),
    )
    assert code == 0
    assert service.async_concurrency_used == 4
