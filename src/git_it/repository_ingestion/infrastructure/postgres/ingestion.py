import psycopg

from git_it.repository_ingestion.application.ports import IngestionRunRecord

from ._common import _bool_to_int, _record_from_row


class PostgresIngestionRunStore:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def save_ingestion_run(self, record: IngestionRunRecord) -> None:
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                """
                INSERT INTO ingestion_runs (
                    run_id, repository_id, canonical_url, status, started_at,
                    completed_at, error_code, error_stage, retryable, safe_message
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    _bool_to_int(record.retryable),
                    record.safe_message,
                ),
            )
            conn.commit()

    def get_ingestion_run(self, run_id: str) -> IngestionRunRecord | None:
        with psycopg.connect(self._conninfo) as conn:
            row = conn.execute(
                """
                SELECT run_id, repository_id, canonical_url, status, started_at,
                       completed_at, error_code, error_stage, retryable, safe_message
                FROM ingestion_runs
                WHERE run_id = %s
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
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                """
                SELECT run_id, repository_id, canonical_url, status, started_at,
                       completed_at, error_code, error_stage, retryable, safe_message
                FROM ingestion_runs
                WHERE repository_id = %s
                ORDER BY started_at ASC, run_id ASC
                """,
                (repository_id,),
            ).fetchall()
        return [_record_from_row(row) for row in rows]
