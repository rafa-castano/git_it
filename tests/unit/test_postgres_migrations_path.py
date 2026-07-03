"""Regression test for the PostgreSQL migrations-file path resolution (batch 105).

`initialize()` locates `migrations/001_initial.sql` via `Path(__file__).parents[N]`.
When the postgres adapters were split into a package (batch 104) the file moved one
directory deeper, and the index math had preserved a PRE-EXISTING off-by-one that
pointed above the repository root — so `initialize()` would raise FileNotFoundError
for anyone running Git It on PostgreSQL. This bug was invisible to the suite because
the only tests that call `initialize()` (test_postgres_adapters.py) are skipped
unless DATABASE_URL is a PostgreSQL URL.

This test exercises ONLY the filesystem path resolution — no PostgreSQL connection —
so it runs unconditionally and guards the migrations file against future moves.
"""

from git_it.repository_ingestion.infrastructure.postgres._common import _migrations_path


def test_migrations_path_resolves_to_existing_file() -> None:
    path = _migrations_path()
    assert path.is_file(), f"migrations SQL not found at resolved path: {path}"


def test_migrations_path_points_at_the_initial_migration() -> None:
    path = _migrations_path()
    assert path.name == "001_initial.sql"
    assert path.parent.name == "migrations"
