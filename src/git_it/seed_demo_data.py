"""Import versioned demo seed data into the configured production backend."""

from __future__ import annotations

import os
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg import sql

from git_it.repository_ingestion.infrastructure.postgres import (
    initialize as postgres_initialize,
)
from git_it.repository_ingestion.infrastructure.workspace import ingestion_workspace_root

ODYSSEUS_REPOSITORY_ID = "repo-f543520f0b824552"
DEFAULT_SEED_ROOT = Path("seed-data") / "odysseus" / "ingestion"


@dataclass(frozen=True)
class TableSeedSpec:
    name: str
    conflict_columns: tuple[str, ...]
    excluded_columns: tuple[str, ...] = ()


TABLE_SPECS: tuple[TableSeedSpec, ...] = (
    TableSeedSpec("ingestion_runs", ("run_id",)),
    TableSeedSpec("commit_facts", ("repository_id", "sha"), excluded_columns=("id",)),
    TableSeedSpec(
        "file_facts",
        ("repository_id", "commit_sha", "file_path"),
        excluded_columns=("id",),
    ),
    TableSeedSpec(
        "commit_analyses",
        ("repository_id", "commit_sha"),
        excluded_columns=("id",),
    ),
    TableSeedSpec("case_studies", ("repository_id", "audience")),
    TableSeedSpec("repository_synopsis", ("repository_id",)),
    TableSeedSpec("github_context", ("repository_id", "commit_sha")),
    TableSeedSpec("repo_metadata", ("repository_id",)),
    TableSeedSpec("default_branch_metadata", ("repository_id",)),
    TableSeedSpec("project_docs", ("repository_id",)),
    TableSeedSpec("discussion_evidence", ("repository_id", "discussion_id")),
    TableSeedSpec("release_evidence", ("repository_id", "tag_name")),
    TableSeedSpec("advisory_evidence", ("repository_id", "ghsa_id")),
    TableSeedSpec("embedding_vectors", ("repository_id", "source_type", "source_id")),
)


def main() -> int:
    conninfo = os.environ.get("DATABASE_URL", "")
    if not (conninfo.startswith("postgresql://") or conninfo.startswith("postgres://")):
        print("DATABASE_URL must point to PostgreSQL before importing demo seed data.")
        return 2

    project_root = Path(os.environ.get("GIT_IT_DATA_DIR") or Path.cwd())
    seed_root = Path(os.environ.get("GIT_IT_SEED_ROOT") or DEFAULT_SEED_ROOT)
    sqlite_path = seed_root / "git-it.sqlite3"
    seed_repo_path = seed_root / "repos" / f"{ODYSSEUS_REPOSITORY_ID}.git"
    target_repo_path = (
        ingestion_workspace_root(project_root) / "repos" / f"{ODYSSEUS_REPOSITORY_ID}.git"
    )

    if not sqlite_path.exists():
        print(f"Seed SQLite not found: {sqlite_path}")
        return 2
    if not seed_repo_path.exists():
        print(f"Seed repository cache not found: {seed_repo_path}")
        return 2

    postgres_initialize(conninfo)
    imported = _import_sqlite_seed(sqlite_path=sqlite_path, conninfo=conninfo)
    _copy_repository_cache(seed_repo_path=seed_repo_path, target_repo_path=target_repo_path)

    print(f"Imported Odysseus demo seed rows: {imported}")
    print(f"Copied repository cache to: {target_repo_path}")
    return 0


def _copy_repository_cache(*, seed_repo_path: Path, target_repo_path: Path) -> None:
    target_repo_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(seed_repo_path, target_repo_path, dirs_exist_ok=True)


def _import_sqlite_seed(*, sqlite_path: Path, conninfo: str) -> dict[str, int]:
    imported: dict[str, int] = {}
    with sqlite3.connect(sqlite_path) as sqlite_conn, psycopg.connect(conninfo) as pg_conn:
        for spec in TABLE_SPECS:
            rows = sqlite_conn.execute(f"SELECT * FROM {spec.name}").fetchall()  # noqa: S608
            if not rows:
                imported[spec.name] = 0
                continue

            sqlite_columns = [
                column[1] for column in sqlite_conn.execute(f"PRAGMA table_info({spec.name})")
            ]
            columns = [c for c in sqlite_columns if c not in spec.excluded_columns]
            excluded_indexes = {
                index
                for index, column in enumerate(sqlite_columns)
                if column in spec.excluded_columns
            }
            values = [
                tuple(value for index, value in enumerate(row) if index not in excluded_indexes)
                for row in rows
            ]
            query = _insert_query(
                table=spec.name,
                columns=tuple(columns),
                conflict_columns=spec.conflict_columns,
            )
            with pg_conn.cursor() as cursor:
                cursor.executemany(query, values)
                imported[spec.name] = cursor.rowcount or 0
        pg_conn.commit()
    return imported


def _insert_query(
    *,
    table: str,
    columns: tuple[str, ...],
    conflict_columns: tuple[str, ...],
) -> sql.Composed:
    placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in columns)
    return sql.SQL(
        "INSERT INTO {table} ({columns}) VALUES ({placeholders}) "
        "ON CONFLICT ({conflict_columns}) DO NOTHING"
    ).format(
        table=sql.Identifier(table),
        columns=sql.SQL(", ").join(sql.Identifier(column) for column in columns),
        placeholders=placeholders,
        conflict_columns=sql.SQL(", ").join(sql.Identifier(column) for column in conflict_columns),
    )


if __name__ == "__main__":
    raise SystemExit(main())
