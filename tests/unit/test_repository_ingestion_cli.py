from dataclasses import dataclass
from pathlib import Path

import pytest

from git_it.cli import main, repository_id_for_url
from git_it.repository_ingestion.application.service import IngestionResult


@dataclass
class RecordingIngestionService:
    result: IngestionResult
    ingested_urls: list[str]

    def ingest(self, raw_url: str) -> IngestionResult:
        self.ingested_urls.append(raw_url)
        return self.result


def test_repository_id_for_url_is_deterministic_and_path_safe() -> None:
    repository_id = repository_id_for_url("https://github.com/owner/repo.git")

    assert repository_id.startswith("repo-")
    assert repository_id == repository_id_for_url("https://github.com/owner/repo.git")
    assert "/" not in repository_id
    assert "\\" not in repository_id


def test_ingest_cli_invokes_application_service_and_prints_human_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = RecordingIngestionService(
        result=IngestionResult(
            status="CLONING_OR_FETCHING",
            error_code=None,
            stage="CLONING_OR_FETCHING",
            retryable=False,
            safe_message=None,
        ),
        ingested_urls=[],
    )
    service_factory_calls: list[tuple[Path, str]] = []

    def service_factory(
        *,
        project_root: Path,
        repository_id: str,
    ) -> RecordingIngestionService:
        service_factory_calls.append((project_root, repository_id))
        return service

    exit_code = main(
        ["ingest", "https://github.com/owner/repo.git"],
        project_root=tmp_path,
        service_factory=service_factory,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert service.ingested_urls == ["https://github.com/owner/repo.git"]
    assert service_factory_calls == [
        (tmp_path, repository_id_for_url("https://github.com/owner/repo.git"))
    ]
    assert "Ingestion status: CLONING_OR_FETCHING" in captured.out


def test_ingest_cli_returns_non_zero_and_prints_safe_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = RecordingIngestionService(
        result=IngestionResult(
            status="FAILED_VALIDATION",
            error_code="INVALID_URL",
            stage="VALIDATING_URL",
            retryable=False,
            safe_message="Repository URL must be a public GitHub HTTPS repository URL.",
        ),
        ingested_urls=[],
    )

    def service_factory(
        *,
        project_root: Path,
        repository_id: str,
    ) -> RecordingIngestionService:
        return service

    exit_code = main(
        ["ingest", "not-a-url"],
        project_root=tmp_path,
        service_factory=service_factory,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Ingestion failed: INVALID_URL" in captured.out
    assert "Repository URL must be a public GitHub HTTPS repository URL." in captured.out
    assert "Traceback" not in captured.out


def test_ingest_cli_prints_run_id_in_success_output_when_present(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = RecordingIngestionService(
        result=IngestionResult(
            status="CLONING_OR_FETCHING",
            error_code=None,
            stage="CLONING_OR_FETCHING",
            retryable=False,
            safe_message=None,
            run_id="run-abc123",
        ),
        ingested_urls=[],
    )

    def service_factory(*, project_root: Path, repository_id: str) -> RecordingIngestionService:
        return service

    exit_code = main(
        ["ingest", "https://github.com/owner/repo"],
        project_root=tmp_path,
        service_factory=service_factory,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Ingestion status: CLONING_OR_FETCHING" in captured.out
    assert "Run ID: run-abc123" in captured.out


def test_ingest_cli_prints_run_id_in_failure_output_when_present(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = RecordingIngestionService(
        result=IngestionResult(
            status="FAILED_VALIDATION",
            error_code="INVALID_URL",
            stage="VALIDATING_URL",
            retryable=False,
            safe_message="Repository URL must be a public GitHub HTTPS repository URL.",
            run_id="run-abc123",
        ),
        ingested_urls=[],
    )

    def service_factory(*, project_root: Path, repository_id: str) -> RecordingIngestionService:
        return service

    exit_code = main(
        ["ingest", "not-a-url"],
        project_root=tmp_path,
        service_factory=service_factory,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Ingestion failed: INVALID_URL" in captured.out
    assert "Run ID: run-abc123" in captured.out
    assert "Repository URL must be a public GitHub HTTPS repository URL." in captured.out


def test_ingest_cli_prints_commit_count_in_success_output_when_present(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = RecordingIngestionService(
        result=IngestionResult(
            status="CLONING_OR_FETCHING",
            error_code=None,
            stage="CLONING_OR_FETCHING",
            retryable=False,
            safe_message=None,
            commits_inserted=3,
            commits_reused=2,
        ),
        ingested_urls=[],
    )

    def service_factory(*, project_root: Path, repository_id: str) -> RecordingIngestionService:
        return service

    exit_code = main(
        ["ingest", "https://github.com/owner/repo"],
        project_root=tmp_path,
        service_factory=service_factory,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Commits: 3 inserted, 2 reused" in captured.out


def test_ingest_cli_omits_commit_count_when_absent(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = RecordingIngestionService(
        result=IngestionResult(
            status="CLONING_OR_FETCHING",
            error_code=None,
            stage="CLONING_OR_FETCHING",
            retryable=False,
            safe_message=None,
            commits_inserted=None,
            commits_reused=None,
        ),
        ingested_urls=[],
    )

    def service_factory(*, project_root: Path, repository_id: str) -> RecordingIngestionService:
        return service

    main(
        ["ingest", "https://github.com/owner/repo"],
        project_root=tmp_path,
        service_factory=service_factory,
    )

    captured = capsys.readouterr()
    assert "Commits:" not in captured.out


def test_ingest_cli_prints_repository_and_canonical_url_in_success_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = RecordingIngestionService(
        result=IngestionResult(
            status="CLONING_OR_FETCHING",
            error_code=None,
            stage="CLONING_OR_FETCHING",
            retryable=False,
            safe_message=None,
            canonical_url="https://github.com/owner/repo",
        ),
        ingested_urls=[],
    )

    def service_factory(*, project_root: Path, repository_id: str) -> RecordingIngestionService:
        return service

    exit_code = main(
        ["ingest", "https://github.com/owner/repo"],
        project_root=tmp_path,
        service_factory=service_factory,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Repository: owner/repo" in captured.out
    assert "Canonical URL: https://github.com/owner/repo" in captured.out


def test_ingest_cli_omits_repository_lines_when_canonical_url_is_absent(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = RecordingIngestionService(
        result=IngestionResult(
            status="CLONING_OR_FETCHING",
            error_code=None,
            stage="CLONING_OR_FETCHING",
            retryable=False,
            safe_message=None,
            canonical_url=None,
        ),
        ingested_urls=[],
    )

    def service_factory(*, project_root: Path, repository_id: str) -> RecordingIngestionService:
        return service

    main(
        ["ingest", "https://github.com/owner/repo"],
        project_root=tmp_path,
        service_factory=service_factory,
    )

    captured = capsys.readouterr()
    assert "Repository:" not in captured.out
    assert "Canonical URL:" not in captured.out


def test_ingest_cli_omits_run_id_line_when_run_id_is_absent(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = RecordingIngestionService(
        result=IngestionResult(
            status="CLONING_OR_FETCHING",
            error_code=None,
            stage="CLONING_OR_FETCHING",
            retryable=False,
            safe_message=None,
            run_id=None,
        ),
        ingested_urls=[],
    )

    def service_factory(*, project_root: Path, repository_id: str) -> RecordingIngestionService:
        return service

    main(
        ["ingest", "https://github.com/owner/repo"],
        project_root=tmp_path,
        service_factory=service_factory,
    )

    captured = capsys.readouterr()
    assert "Run ID:" not in captured.out


def test_cli_rejects_unknown_command_without_calling_service(tmp_path: Path) -> None:
    def service_factory(
        *,
        project_root: Path,
        repository_id: str,
    ) -> RecordingIngestionService:
        raise AssertionError("service factory should not be called")

    with pytest.raises(SystemExit) as raised_error:
        main(["unknown"], project_root=tmp_path, service_factory=service_factory)

    assert raised_error.value.code == 2
