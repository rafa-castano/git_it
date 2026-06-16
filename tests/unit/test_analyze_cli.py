from pathlib import Path

import pytest

from git_it.cli import main
from git_it.repository_ingestion.application.analysis_service import AnalysisResult


class RecordingAnalysisService:
    def __init__(self, result: AnalysisResult) -> None:
        self._result = result
        self.calls: list[tuple[str, int | None]] = []

    def analyze(self, repository_id: str, *, limit: int | None = None) -> AnalysisResult:
        self.calls.append((repository_id, limit))
        return self._result


def test_analyze_cli_prints_analysis_text(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = RecordingAnalysisService(
        AnalysisResult(
            repository_id="repo-1",
            commit_count=10,
            analysis="Key decisions: moved to microservices.",
        )
    )

    def factory(*, project_root: Path, repository_id: str, model: str) -> RecordingAnalysisService:
        return service

    exit_code = main(
        ["analyze", "https://github.com/owner/repo"],
        project_root=tmp_path,
        analysis_factory=factory,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Key decisions: moved to microservices." in captured.out


def test_analyze_cli_shows_commit_count(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = RecordingAnalysisService(
        AnalysisResult(repository_id="repo-1", commit_count=42, analysis="Summary here.")
    )

    def factory(*, project_root: Path, repository_id: str, model: str) -> RecordingAnalysisService:
        return service

    main(
        ["analyze", "https://github.com/owner/repo"],
        project_root=tmp_path,
        analysis_factory=factory,
    )

    captured = capsys.readouterr()
    assert "42" in captured.out


def test_analyze_cli_shows_no_commits_message_when_count_is_zero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = RecordingAnalysisService(
        AnalysisResult(repository_id="repo-1", commit_count=0, analysis="")
    )

    def factory(*, project_root: Path, repository_id: str, model: str) -> RecordingAnalysisService:
        return service

    exit_code = main(
        ["analyze", "https://github.com/owner/repo"],
        project_root=tmp_path,
        analysis_factory=factory,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "No commits" in captured.out


def test_analyze_cli_passes_model_flag_to_factory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    received_models: list[str] = []
    service = RecordingAnalysisService(
        AnalysisResult(repository_id="repo-1", commit_count=1, analysis="x")
    )

    def factory(*, project_root: Path, repository_id: str, model: str) -> RecordingAnalysisService:
        received_models.append(model)
        return service

    main(
        ["analyze", "--model", "openai/gpt-4o-mini", "https://github.com/owner/repo"],
        project_root=tmp_path,
        analysis_factory=factory,
    )

    assert received_models == ["openai/gpt-4o-mini"]


def test_analyze_cli_passes_limit_to_service(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = RecordingAnalysisService(
        AnalysisResult(repository_id="repo-1", commit_count=5, analysis="x")
    )

    def factory(*, project_root: Path, repository_id: str, model: str) -> RecordingAnalysisService:
        return service

    main(
        ["analyze", "--limit", "25", "https://github.com/owner/repo"],
        project_root=tmp_path,
        analysis_factory=factory,
    )

    assert service.calls[0][1] == 25
