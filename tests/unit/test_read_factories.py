"""Tests for the composition-layer read factories — spec 014.

The API read endpoints must select their database backend (SQLite or
PostgreSQL) through composition-layer factories that honour DATABASE_URL,
exactly as the write paths already do via _get_db_backend().

No network, no Docker, no live Postgres: backend-selection tests only assert
the constructed adapter type, and the fail-loud tests point DATABASE_URL at an
unreachable local port with a 1-second connect timeout.
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from git_it.repository_ingestion import composition
from git_it.repository_ingestion.infrastructure import postgres as postgres_infra
from git_it.repository_ingestion.infrastructure import sqlite as sqlite_infra

# Port 9 (discard) is closed on developer machines — the connection is refused
# immediately; connect_timeout=1 bounds the worst case. The fake password lets
# tests assert that credentials never leak into API responses.
UNREACHABLE_PG_URL = "postgresql://gituser:secretpass@127.0.0.1:9/gitit?connect_timeout=1"

# (factory name, SQLite adapter class name, Postgres adapter class name)
READ_FACTORIES = [
    ("build_repository_list_reader", "SqliteRepositoryListReader", "PostgresRepositoryListReader"),
    ("build_case_study_store", "SqliteCaseStudyStore", "PostgresCaseStudyStore"),
    ("build_commit_count_reader", "SqliteCommitCountReader", "PostgresCommitCountReader"),
    (
        "build_commit_with_analysis_reader",
        "SqliteCommitWithAnalysisReader",
        "PostgresCommitWithAnalysisReader",
    ),
    ("build_contributor_reader", "SqliteContributorReader", "PostgresContributorReader"),
    ("build_ingestion_run_store", "SqliteIngestionRunStore", "PostgresIngestionRunStore"),
    ("build_repository_deleter", "SqliteRepositoryDeleter", "PostgresRepositoryDeleter"),
]


# ---------------------------------------------------------------------------
# RED: factory backend selection per DATABASE_URL
# GREEN: build_* read factories in composition.py
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("factory_name", "sqlite_cls", "postgres_cls"), READ_FACTORIES)
def test_read_factory_selects_sqlite_when_database_url_unset(
    factory_name: str,
    sqlite_cls: str,
    postgres_cls: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without DATABASE_URL the factory returns the SQLite adapter (default backend)."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    factory = getattr(composition, factory_name)

    adapter = factory(project_root=tmp_path)

    assert isinstance(adapter, getattr(sqlite_infra, sqlite_cls))


@pytest.mark.parametrize(("factory_name", "sqlite_cls", "postgres_cls"), READ_FACTORIES)
def test_read_factory_selects_postgres_when_database_url_is_postgres(
    factory_name: str,
    sqlite_cls: str,
    postgres_cls: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A postgresql:// DATABASE_URL selects the Postgres adapter (construction only)."""
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_PG_URL)
    factory = getattr(composition, factory_name)

    adapter = factory(project_root=tmp_path)

    assert isinstance(adapter, getattr(postgres_infra, postgres_cls))


@pytest.mark.parametrize(("factory_name", "sqlite_cls", "postgres_cls"), READ_FACTORIES)
def test_read_factory_ignores_non_postgres_database_url(
    factory_name: str,
    sqlite_cls: str,
    postgres_cls: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-Postgres DATABASE_URL falls back to SQLite, matching _get_db_backend."""
    monkeypatch.setenv("DATABASE_URL", "mysql://u:p@localhost/db")
    factory = getattr(composition, factory_name)

    adapter = factory(project_root=tmp_path)

    assert isinstance(adapter, getattr(sqlite_infra, sqlite_cls))


# ---------------------------------------------------------------------------
# RED: backend-aware "database provisioned" check
# GREEN: composition.database_is_provisioned
# ---------------------------------------------------------------------------


def test_database_is_provisioned_false_for_sqlite_without_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SQLite backend: no database file means not provisioned (today's 404/empty path)."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert composition.database_is_provisioned(project_root=tmp_path) is False


def test_database_is_provisioned_true_for_sqlite_with_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SQLite backend: an existing database file means provisioned."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db = tmp_path / ".data" / "git-it" / "ingestion" / "git-it.sqlite3"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.touch()
    assert composition.database_is_provisioned(project_root=tmp_path) is True


def test_database_is_provisioned_true_for_postgres_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Postgres backend: provisioning is not a file check — reachability fails loud later."""
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_PG_URL)
    assert composition.database_is_provisioned(project_root=tmp_path) is True


# ---------------------------------------------------------------------------
# RED: fail-loud API behaviour when Postgres is selected but unreachable
# GREEN: route handlers use the factories + app-level OperationalError handler
# ---------------------------------------------------------------------------


@pytest.fixture()
def pg_unreachable_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from git_it.api.app import create_app

    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_PG_URL)
    monkeypatch.delenv("GIT_IT_API_KEY", raising=False)
    app = create_app(project_root=tmp_path)
    return TestClient(app)


def _assert_fails_loud(response) -> None:  # type: ignore[no-untyped-def]
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "PostgreSQL" in detail
    assert "DATABASE_URL" in detail
    # Never leak the connection string or its credentials.
    assert "secretpass" not in response.text
    assert UNREACHABLE_PG_URL not in response.text


def test_list_repos_fails_loud_when_postgres_unreachable(
    pg_unreachable_client: TestClient,
) -> None:
    _assert_fails_loud(pg_unreachable_client.get("/api/repos"))


def test_get_case_study_fails_loud_when_postgres_unreachable(
    pg_unreachable_client: TestClient,
) -> None:
    _assert_fails_loud(pg_unreachable_client.get("/api/repos/repo-abc/case-study"))


def test_get_commits_fails_loud_when_postgres_unreachable(
    pg_unreachable_client: TestClient,
) -> None:
    _assert_fails_loud(pg_unreachable_client.get("/api/repos/repo-abc/commits"))


def test_estimate_analyze_fails_loud_when_postgres_unreachable(
    pg_unreachable_client: TestClient,
) -> None:
    _assert_fails_loud(pg_unreachable_client.get("/api/repos/repo-abc/analyze/estimate"))


def test_get_contributors_fails_loud_when_postgres_unreachable(
    pg_unreachable_client: TestClient,
) -> None:
    _assert_fails_loud(pg_unreachable_client.get("/api/repos/repo-abc/contributors"))


def test_delete_repo_fails_loud_when_postgres_unreachable(
    pg_unreachable_client: TestClient,
) -> None:
    _assert_fails_loud(pg_unreachable_client.delete("/api/repos/repo-abc"))


def test_postgres_backend_never_falls_back_to_existing_sqlite_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A leftover SQLite file with data must NOT be served when Postgres is selected."""
    from git_it.api.app import create_app

    db = tmp_path / ".data" / "git-it" / "ingestion" / "git-it.sqlite3"
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE ingestion_runs (
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
        conn.execute(
            "INSERT INTO ingestion_runs (run_id, repository_id, canonical_url, status, started_at)"
            " VALUES (?, ?, ?, ?, ?)",
            ("run-1", "repo-abc", "https://github.com/test/repo", "COMPLETED", "2024-01-01"),
        )

    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_PG_URL)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.get("/api/repos")

    assert response.status_code == 503  # not a 200 built from the SQLite file
