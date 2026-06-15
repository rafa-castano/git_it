import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IngestionRunRecord:
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


class SqliteIngestionRunStore:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ingestion_runs (
                    run_id TEXT PRIMARY KEY,
                    repository_id TEXT NOT NULL,
                    canonical_url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    error_code TEXT,
                    error_stage TEXT,
                    retryable INTEGER,
                    safe_message TEXT
                )
                """
            )

    def save_ingestion_run(self, record: IngestionRunRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ingestion_runs (
                    run_id,
                    repository_id,
                    canonical_url,
                    status,
                    started_at,
                    completed_at,
                    error_code,
                    error_stage,
                    retryable,
                    safe_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.run_id,
                    record.repository_id,
                    record.canonical_url,
                    record.status,
                    record.started_at,
                    record.completed_at,
                    record.error_code,
                    record.error_stage,
                    _bool_to_sqlite(record.retryable),
                    record.safe_message,
                ),
            )

    def get_ingestion_run(self, run_id: str) -> IngestionRunRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    run_id,
                    repository_id,
                    canonical_url,
                    status,
                    started_at,
                    completed_at,
                    error_code,
                    error_stage,
                    retryable,
                    safe_message
                FROM ingestion_runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()

        if row is None:
            return None
        return _record_from_row(row)

    def list_ingestion_runs_for_repository(
        self,
        repository_id: str,
    ) -> list[IngestionRunRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    run_id,
                    repository_id,
                    canonical_url,
                    status,
                    started_at,
                    completed_at,
                    error_code,
                    error_stage,
                    retryable,
                    safe_message
                FROM ingestion_runs
                WHERE repository_id = ?
                ORDER BY started_at ASC, run_id ASC
                """,
                (repository_id,),
            ).fetchall()

        return [_record_from_row(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._database_path)


def _record_from_row(row: tuple[object, ...]) -> IngestionRunRecord:
    return IngestionRunRecord(
        run_id=str(row[0]),
        repository_id=str(row[1]),
        canonical_url=str(row[2]),
        status=str(row[3]),
        started_at=str(row[4]),
        completed_at=_optional_str(row[5]),
        error_code=_optional_str(row[6]),
        error_stage=_optional_str(row[7]),
        retryable=_sqlite_to_bool(row[8]),
        safe_message=_optional_str(row[9]),
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _bool_to_sqlite(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def _sqlite_to_bool(value: object) -> bool | None:
    if value is None:
        return None
    return bool(value)
