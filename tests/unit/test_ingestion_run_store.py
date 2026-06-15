from pathlib import Path

from git_it.repository_ingestion.application.ports import IngestionRunRecord
from git_it.repository_ingestion.application.query_service import (
    IngestionRunSummaryDTO,
    RepositoryIngestionQueryService,
)
from git_it.repository_ingestion.infrastructure.sqlite import SqliteIngestionRunStore


def test_sqlite_ingestion_run_store_round_trips_run_summary(tmp_path: Path) -> None:
    store = SqliteIngestionRunStore(tmp_path / "git-it.db")
    store.initialize()
    record = IngestionRunRecord(
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

    store.save_ingestion_run(record)

    assert store.get_ingestion_run("run-1") == record


def test_sqlite_ingestion_run_store_records_failure_details(tmp_path: Path) -> None:
    store = SqliteIngestionRunStore(tmp_path / "git-it.db")
    store.initialize()
    record = IngestionRunRecord(
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

    store.save_ingestion_run(record)

    assert store.get_ingestion_run("run-1") == record


def test_sqlite_ingestion_run_store_keeps_runs_append_only_per_repository(
    tmp_path: Path,
) -> None:
    store = SqliteIngestionRunStore(tmp_path / "git-it.db")
    store.initialize()
    first_run = IngestionRunRecord(
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
    second_run = IngestionRunRecord(
        run_id="run-2",
        repository_id="repo-1",
        canonical_url="https://github.com/owner/repo",
        status="COMPLETED",
        started_at="2026-06-15T10:10:00Z",
        completed_at="2026-06-15T10:11:00Z",
        error_code=None,
        error_stage=None,
        retryable=None,
        safe_message=None,
    )

    store.save_ingestion_run(first_run)
    store.save_ingestion_run(second_run)

    assert store.list_ingestion_runs_for_repository("repo-1") == [first_run, second_run]


def test_sqlite_ingestion_run_store_can_back_query_service(tmp_path: Path) -> None:
    store = SqliteIngestionRunStore(tmp_path / "git-it.db")
    store.initialize()
    store.save_ingestion_run(
        IngestionRunRecord(
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
    )
    query_service = RepositoryIngestionQueryService(reader=store)

    assert query_service.get_ingestion_run_summary("run-1") == IngestionRunSummaryDTO(
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
