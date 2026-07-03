import json
import sqlite3
from pathlib import Path

from git_it.repository_ingestion.application.commit_query_service import CommitRecord
from git_it.repository_ingestion.application.ports import (
    CommitPersistenceResult,
    CommitSummaryRecord,
    CommitWithAnalysisRecord,
)
from git_it.repository_ingestion.domain.commits import ExtractedCommit


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
                    author_email TEXT NOT NULL DEFAULT '',
                    UNIQUE(repository_id, sha)
                )
                """
            )
            # Migrate existing DBs that pre-date author_email column
            try:
                connection.execute(
                    "ALTER TABLE commit_facts ADD COLUMN author_email TEXT NOT NULL DEFAULT ''"
                )
            except sqlite3.OperationalError as e:
                if (
                    "duplicate column name" not in str(e).lower()
                    and "already exists" not in str(e).lower()
                ):
                    raise

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
                        parent_shas,
                        author_email
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        repository_id,
                        commit.sha,
                        commit.committed_at,
                        commit.message,
                        commit.author_name,
                        commit.committer_name,
                        json.dumps(list(commit.parent_shas)),
                        commit.author_email,
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

    def get_commit_date_map(self, repository_id: str) -> dict[str, str]:
        with sqlite3.connect(self._database_path) as connection:
            rows = connection.execute(
                "SELECT sha, committed_at FROM commit_facts WHERE repository_id = ?",
                (repository_id,),
            ).fetchall()
        return {str(row[0]): str(row[1]) for row in rows}

    def list_commit_messages(self, repository_id: str) -> list[CommitSummaryRecord]:
        with sqlite3.connect(self._database_path) as connection:
            rows = connection.execute(
                "SELECT sha, message FROM commit_facts WHERE repository_id = ?",
                (repository_id,),
            ).fetchall()
        return [CommitSummaryRecord(sha=str(row[0]), message=str(row[1])) for row in rows]

    def list_commits_for_repository(
        self,
        repository_id: str,
        *,
        limit: int | None = None,
        order: str = "newest",
        since: str | None = None,
        until: str | None = None,
    ) -> list[CommitRecord]:
        if order not in ("newest", "oldest"):
            raise ValueError(f"Invalid order value: {order!r}")
        order_dir = "ASC" if order == "oldest" else "DESC"
        conditions = ["repository_id = ?"]
        params: list[object] = [repository_id]
        if since is not None:
            conditions.append("substr(committed_at, 1, 10) >= ?")
            params.append(since)
        if until is not None:
            conditions.append("substr(committed_at, 1, 10) <= ?")
            params.append(until)
        where = " AND ".join(conditions)
        query = f"""
            SELECT sha, committed_at, message, author_name, committer_name, parent_shas
            FROM commit_facts
            WHERE {where}
            ORDER BY committed_at {order_dir}
        """
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
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


class SqliteCommitCountReader:
    """Read-side adapter: returns commit and analysis counts for a repository."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def count_commits(self, repository_id: str) -> int:
        with sqlite3.connect(self._database_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM commit_facts WHERE repository_id = ?",
                (repository_id,),
            ).fetchone()
        return int(row[0]) if row else 0

    def count_analyses(self, repository_id: str) -> int:
        with sqlite3.connect(self._database_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM commit_analyses WHERE repository_id = ?",
                (repository_id,),
            ).fetchone()
        return int(row[0]) if row else 0


class SqliteCommitWithAnalysisReader:
    """Read-side adapter: returns commits joined with their analysis data."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def count_commits_with_analyses(
        self,
        repository_id: str,
        *,
        category: str | None = None,
    ) -> int:
        """Return the total number of analyzed commits, optionally filtered by category."""
        with sqlite3.connect(self._database_path) as conn:
            if category is not None:
                row = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM commit_analyses ca
                    JOIN commit_facts cf
                      ON cf.sha = ca.commit_sha AND cf.repository_id = ca.repository_id
                    WHERE ca.repository_id = ?
                      AND json_extract(ca.data, '$.category') = ?
                    """,
                    (repository_id, category),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM commit_analyses ca
                    JOIN commit_facts cf
                      ON cf.sha = ca.commit_sha AND cf.repository_id = ca.repository_id
                    WHERE ca.repository_id = ?
                    """,
                    (repository_id,),
                ).fetchone()
        return int(row[0]) if row else 0

    def list_commits_with_analyses(
        self,
        repository_id: str,
        *,
        limit: int,
        order: str = "newest",
        category: str | None = None,
    ) -> list[CommitWithAnalysisRecord]:
        if order not in ("newest", "oldest"):
            raise ValueError(f"Invalid order value: {order!r}")
        order_dir = "ASC" if order == "oldest" else "DESC"
        with sqlite3.connect(self._database_path) as conn:
            if category is not None:
                rows = conn.execute(
                    f"""
                    SELECT cf.sha, cf.message, cf.committed_at, ca.data,
                           GROUP_CONCAT(ff.file_path, '|||') AS files
                    FROM commit_analyses ca
                    JOIN commit_facts cf
                      ON cf.sha = ca.commit_sha AND cf.repository_id = ca.repository_id
                    LEFT JOIN file_facts ff
                      ON ff.commit_sha = ca.commit_sha AND ff.repository_id = ca.repository_id
                    WHERE ca.repository_id = ?
                      AND json_extract(ca.data, '$.category') = ?
                    GROUP BY ca.commit_sha, cf.message, cf.committed_at, ca.data
                    ORDER BY cf.committed_at {order_dir}
                    LIMIT ?
                    """,
                    (repository_id, category, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"""
                    SELECT cf.sha, cf.message, cf.committed_at, ca.data,
                           GROUP_CONCAT(ff.file_path, '|||') AS files
                    FROM commit_analyses ca
                    JOIN commit_facts cf
                      ON cf.sha = ca.commit_sha AND cf.repository_id = ca.repository_id
                    LEFT JOIN file_facts ff
                      ON ff.commit_sha = ca.commit_sha AND ff.repository_id = ca.repository_id
                    WHERE ca.repository_id = ?
                    GROUP BY ca.commit_sha, cf.message, cf.committed_at, ca.data
                    ORDER BY cf.committed_at {order_dir}
                    LIMIT ?
                    """,
                    (repository_id, limit),
                ).fetchall()
        return [
            CommitWithAnalysisRecord(
                sha=str(row[0]),
                message=str(row[1]),
                committed_at=str(row[2]),
                analysis_data=str(row[3]) if row[3] is not None else None,
                files_changed=tuple(str(row[4]).split("|||")) if row[4] else (),
            )
            for row in rows
        ]
