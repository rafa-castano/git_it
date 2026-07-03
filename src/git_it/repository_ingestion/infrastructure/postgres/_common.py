"""Shared private helpers and the public ``initialize`` entry point used across the
PostgreSQL infrastructure sub-modules.

Kept dependency-free (leaf module) so every other sub-module in this package can
import from here without risking circular imports.
"""

import re
from pathlib import Path

import psycopg

from git_it.repository_ingestion.application.ports import IngestionRunRecord


def initialize(conninfo: str) -> None:
    """Run migrations/001_initial.sql against the given PostgreSQL connection string."""
    migrations_path = Path(__file__).parents[6] / "migrations" / "001_initial.sql"
    sql = migrations_path.read_text(encoding="utf-8")
    with psycopg.connect(conninfo) as conn:
        conn.execute(sql)
        conn.commit()


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _bool_to_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def _int_to_bool(value: object) -> bool | None:
    if value is None:
        return None
    return bool(value)


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
        retryable=_int_to_bool(row[8]),
        safe_message=_optional_str(row[9]),
    )


def _extract_github_username(email: str) -> str | None:
    m = re.match(r"^\d+\+(.+)@users\.noreply\.github\.com$", email or "")
    if m:
        return m.group(1)
    m = re.match(r"^([^@+]+)@users\.noreply\.github\.com$", email or "")
    if m:
        return m.group(1)
    return None
