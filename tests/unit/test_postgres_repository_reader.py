import pytest

from git_it.repository_ingestion.infrastructure.postgres import repository as repo_module


class _FakeCursor:
    def __init__(self, sql_sink: list[str]) -> None:
        self._sql_sink = sql_sink

    def fetchall(self) -> list[tuple[object, ...]]:
        return [
            (
                "repo-abc",
                "https://github.com/acme/repo",
                "COMPLETED",
                1548,
                231,
                True,
            )
        ]


class _FakeConnection:
    def __init__(self, sql_sink: list[str]) -> None:
        self._sql_sink = sql_sink

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str) -> _FakeCursor:
        self._sql_sink.append(sql)
        return _FakeCursor(self._sql_sink)


def test_postgres_repository_list_reader_avoids_many_table_join_fanout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Postgres must mirror SQLite's scalar reads for /api/repos.

    commit_facts and commit_analyses are both many-row tables per repository.
    Joining both before counting creates a repository-local cross product, which
    is exactly the production-only slow path when Railway uses PostgreSQL.
    """
    executed_sql: list[str] = []

    monkeypatch.setattr(repo_module, "initialize", lambda conninfo: None)
    monkeypatch.setattr(
        repo_module.psycopg,
        "connect",
        lambda conninfo: _FakeConnection(executed_sql),
    )

    records = repo_module.PostgresRepositoryListReader("postgresql://example").list_repositories()

    assert len(records) == 1
    assert records[0].commit_count == 1548
    assert records[0].analysis_count == 231
    query = executed_sql[0]
    assert "LEFT JOIN commit_facts" not in query
    assert "LEFT JOIN commit_analyses" not in query
    assert "SELECT COUNT(*) FROM commit_facts" in query
    assert "SELECT COUNT(*) FROM commit_analyses" in query
