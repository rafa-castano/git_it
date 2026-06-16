from pathlib import Path

import pytest

from git_it.repository_ingestion.application.narrative_service import NarrativeResult
from git_it.repository_ingestion.interfaces.cli import main


def _make_result(narrative: str = "Learning: strong engineering culture.") -> NarrativeResult:
    return NarrativeResult(
        repository_id="repo-1",
        commit_count=5,
        hotspot_count=2,
        narrative=narrative,
    )


class FakeNarrativeService:
    def __init__(self, result: NarrativeResult | None = None) -> None:
        self._result = result or _make_result()
        self.calls: list[str] = []

    def generate(self, repository_id: str, *, force: bool = False) -> NarrativeResult:
        self.calls.append(repository_id)
        return self._result


def _factory(service: FakeNarrativeService):  # type: ignore[no-untyped-def]
    def factory(*, project_root: Path, repository_id: str, model: str) -> FakeNarrativeService:
        return service

    return factory


def test_case_study_exits_zero(tmp_path: Path) -> None:
    code = main(
        ["case-study", "https://github.com/owner/repo"],
        project_root=tmp_path,
        narrative_factory=_factory(FakeNarrativeService()),
    )
    assert code == 0


def test_case_study_prints_narrative(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    service = FakeNarrativeService(result=_make_result("Strong TDD culture detected."))
    main(
        ["case-study", "https://github.com/owner/repo"],
        project_root=tmp_path,
        narrative_factory=_factory(service),
    )
    captured = capsys.readouterr()
    assert "Strong TDD culture detected." in captured.out


def test_case_study_shows_no_analyses_message_when_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = NarrativeResult(repository_id="repo-1", commit_count=0, hotspot_count=0, narrative="")
    service = FakeNarrativeService(result=empty)
    main(
        ["case-study", "https://github.com/owner/repo"],
        project_root=tmp_path,
        narrative_factory=_factory(service),
    )
    captured = capsys.readouterr()
    assert "No" in captured.out


def test_case_study_passes_model_to_factory(tmp_path: Path) -> None:
    received: list[str] = []

    def factory(*, project_root: Path, repository_id: str, model: str) -> FakeNarrativeService:
        received.append(model)
        return FakeNarrativeService()

    main(
        ["case-study", "https://github.com/owner/repo", "--model", "openai/gpt-4o-mini"],
        project_root=tmp_path,
        narrative_factory=factory,
    )
    assert received == ["openai/gpt-4o-mini"]
