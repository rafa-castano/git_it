import json
import sqlite3
from pathlib import Path

from git_it.repository_ingestion.application.commit_query_service import CommitRecord
from git_it.repository_ingestion.application.ports import (
    CommitPersistenceResult,
    FileChurnRecord,
    IngestionRunRecord,
)
from git_it.repository_ingestion.domain.analysis import CommitAnalysis
from git_it.repository_ingestion.domain.commits import ExtractedCommit


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


class SqliteCommitFactStore:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS commit_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repository_id TEXT NOT NULL,
                    sha TEXT NOT NULL,
                    committed_at TEXT NOT NULL,
                    message TEXT NOT NULL,
                    author_name TEXT NOT NULL,
                    committer_name TEXT NOT NULL,
                    parent_shas TEXT NOT NULL,
                    UNIQUE(repository_id, sha)
                )
                """
            )

    def save_commit_facts(
        self,
        commits: list[ExtractedCommit],
        *,
        repository_id: str,
    ) -> CommitPersistenceResult:
        inserted = 0
        reused = 0
        with self._connect() as connection:
            for commit in commits:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO commit_facts (
                        repository_id,
                        sha,
                        committed_at,
                        message,
                        author_name,
                        committer_name,
                        parent_shas
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        repository_id,
                        commit.sha,
                        commit.committed_at,
                        commit.message,
                        commit.author_name,
                        commit.committer_name,
                        json.dumps(list(commit.parent_shas)),
                    ),
                )
                if cursor.rowcount == 1:
                    inserted += 1
                else:
                    reused += 1
        return CommitPersistenceResult(inserted=inserted, reused=reused)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._database_path)


class SqliteFileFactStore:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS file_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repository_id TEXT NOT NULL,
                    commit_sha TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    insertions INTEGER NOT NULL,
                    deletions INTEGER NOT NULL,
                    UNIQUE(repository_id, commit_sha, file_path)
                )
                """
            )

    def save_file_facts(
        self,
        commits: list[ExtractedCommit],
        *,
        repository_id: str,
    ) -> CommitPersistenceResult:
        inserted = 0
        reused = 0
        with self._connect() as connection:
            for commit in commits:
                for change in commit.file_changes:
                    cursor = connection.execute(
                        """
                        INSERT OR IGNORE INTO file_facts (
                            repository_id,
                            commit_sha,
                            file_path,
                            insertions,
                            deletions
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            repository_id,
                            commit.sha,
                            change.path,
                            change.insertions,
                            change.deletions,
                        ),
                    )
                    if cursor.rowcount == 1:
                        inserted += 1
                    else:
                        reused += 1
        return CommitPersistenceResult(inserted=inserted, reused=reused)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._database_path)


class SqliteCommitReader:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def list_commits_for_repository(
        self,
        repository_id: str,
        *,
        limit: int | None = None,
    ) -> list[CommitRecord]:
        query = """
            SELECT sha, committed_at, message, author_name, committer_name, parent_shas
            FROM commit_facts
            WHERE repository_id = ?
            ORDER BY committed_at DESC
        """
        params: tuple = (repository_id,)
        if limit is not None:
            query += " LIMIT ?"
            params = (repository_id, limit)
        with sqlite3.connect(self._database_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [
            CommitRecord(
                repository_id=repository_id,
                sha=str(row[0]),
                committed_at=str(row[1]),
                message=str(row[2]),
                author_name=str(row[3]),
                committer_name=str(row[4]),
                parent_shas=tuple(json.loads(str(row[5]))),
            )
            for row in rows
        ]


class SqliteCommitAnalysisStore:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS commit_analyses (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    repository_id TEXT NOT NULL,
                    commit_sha    TEXT NOT NULL,
                    data          TEXT NOT NULL,
                    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(repository_id, commit_sha)
                )
                """
            )

    def save_analysis(self, analysis: CommitAnalysis, *, repository_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO commit_analyses (repository_id, commit_sha, data)
                VALUES (?, ?, ?)
                """,
                (repository_id, analysis.commit_sha, analysis.model_dump_json()),
            )
        return cursor.rowcount == 1

    def get_analysis(self, *, repository_id: str, commit_sha: str) -> CommitAnalysis | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data FROM commit_analyses WHERE repository_id = ? AND commit_sha = ?",
                (repository_id, commit_sha),
            ).fetchone()
        if row is None:
            return None
        analysis: CommitAnalysis = CommitAnalysis.model_validate_json(str(row[0]))
        return analysis

    def list_analyses(
        self, repository_id: str, *, limit: int | None = None
    ) -> list[CommitAnalysis]:
        query = "SELECT data FROM commit_analyses WHERE repository_id = ? ORDER BY created_at DESC"
        params: tuple[object, ...] = (repository_id,)
        if limit is not None:
            query += " LIMIT ?"
            params = (repository_id, limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [CommitAnalysis.model_validate_json(str(row[0])) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._database_path)


class SqliteFileFactReader:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def get_file_churn(self, repository_id: str) -> list[FileChurnRecord]:
        with sqlite3.connect(self._database_path) as conn:
            rows = conn.execute(
                """
                SELECT
                    file_path,
                    COUNT(DISTINCT commit_sha) AS commit_count,
                    SUM(insertions)            AS total_insertions,
                    SUM(deletions)             AS total_deletions
                FROM file_facts
                WHERE repository_id = ?
                GROUP BY file_path
                ORDER BY commit_count DESC
                """,
                (repository_id,),
            ).fetchall()
        return [
            FileChurnRecord(
                file_path=str(row[0]),
                commit_count=int(row[1]),
                total_insertions=int(row[2]),
                total_deletions=int(row[3]),
            )
            for row in rows
        ]

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
