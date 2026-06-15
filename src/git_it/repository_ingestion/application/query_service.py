from dataclasses import dataclass
from typing import Protocol


class IngestionRunView(Protocol):
    @property
    def run_id(self) -> str: ...

    @property
    def repository_id(self) -> str: ...

    @property
    def canonical_url(self) -> str: ...

    @property
    def status(self) -> str: ...

    @property
    def started_at(self) -> str: ...

    @property
    def completed_at(self) -> str | None: ...

    @property
    def error_code(self) -> str | None: ...

    @property
    def error_stage(self) -> str | None: ...

    @property
    def retryable(self) -> bool | None: ...

    @property
    def safe_message(self) -> str | None: ...


class IngestionRunReader(Protocol):
    def get_ingestion_run(self, run_id: str) -> IngestionRunView | None: ...


@dataclass(frozen=True)
class IngestionStatusDTO:
    run_id: str
    status: str
    error_code: str | None
    error_stage: str | None
    retryable: bool | None
    safe_message: str | None


@dataclass(frozen=True)
class IngestionRunSummaryDTO:
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


class RepositoryIngestionQueryService:
    def __init__(self, *, reader: IngestionRunReader) -> None:
        self._reader = reader

    def get_ingestion_status(self, run_id: str) -> IngestionStatusDTO | None:
        run = self._reader.get_ingestion_run(run_id)
        if run is None:
            return None
        return IngestionStatusDTO(
            run_id=run.run_id,
            status=run.status,
            error_code=run.error_code,
            error_stage=run.error_stage,
            retryable=run.retryable,
            safe_message=run.safe_message,
        )

    def get_ingestion_run_summary(self, run_id: str) -> IngestionRunSummaryDTO | None:
        run = self._reader.get_ingestion_run(run_id)
        if run is None:
            return None
        return IngestionRunSummaryDTO(
            run_id=run.run_id,
            repository_id=run.repository_id,
            canonical_url=run.canonical_url,
            status=run.status,
            started_at=run.started_at,
            completed_at=run.completed_at,
            error_code=run.error_code,
            error_stage=run.error_stage,
            retryable=run.retryable,
            safe_message=run.safe_message,
        )
