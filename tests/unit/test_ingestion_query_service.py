from dataclasses import dataclass

from git_it.repository_ingestion.application.query_service import (
    IngestionRunSummaryDTO,
    IngestionStatusDTO,
    RepositoryIngestionQueryService,
)


@dataclass(frozen=True)
class StoredIngestionRun:
    run_id: str
    repository_id: str
    canonical_url: str
    status: str
    started_at: str
    completed_at: str | None
    error_code: str | None
    error_stage: str | None
    retryable: bool | None
    safe_message: str | None


class FakeIngestionRunReader:
    def __init__(self, runs: dict[str, StoredIngestionRun]) -> None:
        self.runs = runs

    def get_ingestion_run(self, run_id: str) -> StoredIngestionRun | None:
        return self.runs.get(run_id)


def test_get_ingestion_status_returns_stable_status_dto() -> None:
    reader = FakeIngestionRunReader(
        {
            "run-1": StoredIngestionRun(
                run_id="run-1",
                repository_id="repo-1",
                canonical_url="https://github.com/owner/repo",
                status="FAILED_FETCH",
                started_at="2026-06-15T10:00:00Z",
                completed_at="2026-06-15T10:05:00Z",
                error_code="CLONE_TIMEOUT",
                error_stage="CLONING_OR_FETCHING",
                retryable=True,
                safe_message="Repository fetch failed safely before analysis could start.",
            )
        }
    )
    query_service = RepositoryIngestionQueryService(reader=reader)

    status = query_service.get_ingestion_status("run-1")

    assert status == IngestionStatusDTO(
        run_id="run-1",
        status="FAILED_FETCH",
        error_code="CLONE_TIMEOUT",
        error_stage="CLONING_OR_FETCHING",
        retryable=True,
        safe_message="Repository fetch failed safely before analysis could start.",
    )


def test_get_ingestion_status_returns_none_for_unknown_run() -> None:
    query_service = RepositoryIngestionQueryService(reader=FakeIngestionRunReader({}))

    assert query_service.get_ingestion_status("missing-run") is None


def test_get_ingestion_run_summary_returns_stable_summary_dto() -> None:
    reader = FakeIngestionRunReader(
        {
            "run-1": StoredIngestionRun(
                run_id="run-1",
                repository_id="repo-1",
                canonical_url="https://github.com/owner/repo",
                status="COMPLETED",
                started_at="2026-06-15T10:00:00Z",
                completed_at="2026-06-15T10:01:00Z",
                error_code=None,
                error_stage=None,
                retryable=None,
                safe_message=None,
            )
        }
    )
    query_service = RepositoryIngestionQueryService(reader=reader)

    summary = query_service.get_ingestion_run_summary("run-1")

    assert summary == IngestionRunSummaryDTO(
        run_id="run-1",
        repository_id="repo-1",
        canonical_url="https://github.com/owner/repo",
        status="COMPLETED",
        started_at="2026-06-15T10:00:00Z",
        completed_at="2026-06-15T10:01:00Z",
        error_code=None,
        error_stage=None,
        retryable=None,
        safe_message=None,
    )


def test_get_ingestion_run_summary_returns_none_for_unknown_run() -> None:
    query_service = RepositoryIngestionQueryService(reader=FakeIngestionRunReader({}))

    assert query_service.get_ingestion_run_summary("missing-run") is None
