import json

import psycopg

from git_it.repository_ingestion.application.commit_query_service import CommitRecord
from git_it.repository_ingestion.application.ports import (
    CommitPersistenceResult,
    CommitSummaryRecord,
    CommitWithAnalysisRecord,
)
from git_it.repository_ingestion.domain.commits import ExtractedCommit


class PostgresCommitStore:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def save_commit_facts(
        self,
        commits: list[ExtractedCommit],
        *,
        repository_id: str,
    ) -> CommitPersistenceResult:
        inserted = 0
        reused = 0
        with psycopg.connect(self._conninfo) as conn:
            for commit in commits:
                cursor = conn.execute(
                    """
                    INSERT INTO commit_facts (
                        repository_id, sha, committed_at, message,
                        author_name, committer_name, parent_shas, author_email
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (repository_id, sha) DO NOTHING
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
            conn.commit()
        return CommitPersistenceResult(inserted=inserted, reused=reused)


class PostgresCommitReader:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def get_commit_date_map(self, repository_id: str) -> dict[str, str]:
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                "SELECT sha, committed_at FROM commit_facts WHERE repository_id = %s",
                (repository_id,),
            ).fetchall()
        return {str(row[0]): str(row[1]) for row in rows}

    def list_commit_messages(self, repository_id: str) -> list[CommitSummaryRecord]:
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                "SELECT sha, message FROM commit_facts WHERE repository_id = %s",
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
        conditions = ["repository_id = %s"]
        params: list[object] = [repository_id]
        if since is not None:
            conditions.append("SUBSTR(committed_at, 1, 10) >= %s")
            params.append(since)
        if until is not None:
            conditions.append("SUBSTR(committed_at, 1, 10) <= %s")
            params.append(until)
        where = " AND ".join(conditions)
        query = f"""
            SELECT sha, committed_at, message, author_name, committer_name, parent_shas
            FROM commit_facts
            WHERE {where}
            ORDER BY committed_at {order_dir}
        """
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(query, params).fetchall()
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


class PostgresCommitCountReader:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def count_commits(self, repository_id: str) -> int:
        with psycopg.connect(self._conninfo) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM commit_facts WHERE repository_id = %s",
                (repository_id,),
            ).fetchone()
        return int(row[0]) if row else 0

    def count_analyses(self, repository_id: str) -> int:
        with psycopg.connect(self._conninfo) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM commit_analyses WHERE repository_id = %s",
                (repository_id,),
            ).fetchone()
        return int(row[0]) if row else 0


class PostgresCommitWithAnalysisReader:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def count_commits_with_analyses(
        self,
        repository_id: str,
        *,
        category: str | None = None,
    ) -> int:
        """Return the total number of analyzed commits, optionally filtered by category."""
        with psycopg.connect(self._conninfo) as conn:
            if category is not None:
                row = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM commit_analyses ca
                    JOIN commit_facts cf
                      ON cf.sha = ca.commit_sha AND cf.repository_id = ca.repository_id
                    WHERE ca.repository_id = %s
                      AND ca.data::json->>'category' = %s
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
                    WHERE ca.repository_id = %s
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
        with psycopg.connect(self._conninfo) as conn:
            if category is not None:
                rows = conn.execute(
                    f"""
                    SELECT cf.sha, cf.message, cf.committed_at, ca.data,
                           STRING_AGG(ff.file_path, '|||') AS files
                    FROM commit_analyses ca
                    JOIN commit_facts cf
                      ON cf.sha = ca.commit_sha AND cf.repository_id = ca.repository_id
                    LEFT JOIN file_facts ff
                      ON ff.commit_sha = ca.commit_sha AND ff.repository_id = ca.repository_id
                    WHERE ca.repository_id = %s
                      AND ca.data::json->>'category' = %s
                    GROUP BY cf.sha, cf.message, cf.committed_at, ca.data
                    ORDER BY cf.committed_at {order_dir}
                    LIMIT %s
                    """,
                    (repository_id, category, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"""
                    SELECT cf.sha, cf.message, cf.committed_at, ca.data,
                           STRING_AGG(ff.file_path, '|||') AS files
                    FROM commit_analyses ca
                    JOIN commit_facts cf
                      ON cf.sha = ca.commit_sha AND cf.repository_id = ca.repository_id
                    LEFT JOIN file_facts ff
                      ON ff.commit_sha = ca.commit_sha AND ff.repository_id = ca.repository_id
                    WHERE ca.repository_id = %s
                    GROUP BY cf.sha, cf.message, cf.committed_at, ca.data
                    ORDER BY cf.committed_at {order_dir}
                    LIMIT %s
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
