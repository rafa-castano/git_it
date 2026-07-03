import sqlite3
from pathlib import Path

from git_it.repository_ingestion.application.ports import (
    CommitPersistenceResult,
    FileChurnRecord,
    FileOwnershipRecord,
)
from git_it.repository_ingestion.domain.commits import ExtractedCommit


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

    def get_file_evidence_commits(
        self, repository_id: str, *, limit: int = 5
    ) -> dict[str, tuple[str, ...]]:
        with sqlite3.connect(self._database_path) as conn:
            rows = conn.execute(
                """
                SELECT f.file_path, c.sha
                FROM file_facts f
                JOIN commit_facts c ON c.sha = f.commit_sha AND c.repository_id = f.repository_id
                WHERE f.repository_id = ?
                ORDER BY f.file_path, c.committed_at DESC
                """,
                (repository_id,),
            ).fetchall()
        result: dict[str, list[str]] = {}
        for file_path, sha in rows:
            fp = str(file_path)
            bucket = result.setdefault(fp, [])
            if len(bucket) < limit:
                bucket.append(str(sha))
        return {fp: tuple(shas) for fp, shas in result.items()}

    def get_file_ownership(self, repository_id: str) -> list[FileOwnershipRecord]:
        with sqlite3.connect(self._database_path) as conn:
            rows = conn.execute(
                """
                SELECT
                    ff.file_path,
                    COUNT(DISTINCT cf.author_name) AS author_count,
                    COUNT(DISTINCT ff.commit_sha)  AS commit_count
                FROM file_facts ff
                JOIN commit_facts cf
                  ON ff.repository_id = cf.repository_id AND ff.commit_sha = cf.sha
                WHERE ff.repository_id = ?
                GROUP BY ff.file_path
                """,
                (repository_id,),
            ).fetchall()
        return [
            FileOwnershipRecord(
                file_path=str(row[0]),
                author_count=int(row[1]),
                commit_count=int(row[2]),
            )
            for row in rows
        ]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._database_path)
