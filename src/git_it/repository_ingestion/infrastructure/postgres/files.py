import psycopg

from git_it.repository_ingestion.application.ports import (
    CommitPersistenceResult,
    FileChurnRecord,
    FileOwnershipRecord,
)
from git_it.repository_ingestion.domain.commits import ExtractedCommit


class PostgresFileFactStore:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def save_file_facts(
        self,
        commits: list[ExtractedCommit],
        *,
        repository_id: str,
    ) -> CommitPersistenceResult:
        inserted = 0
        reused = 0
        with psycopg.connect(self._conninfo) as conn:
            for commit in commits:
                for change in commit.file_changes:
                    cursor = conn.execute(
                        """
                        INSERT INTO file_facts (
                            repository_id, commit_sha, file_path, insertions, deletions
                        ) VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (repository_id, commit_sha, file_path) DO NOTHING
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
            conn.commit()
        return CommitPersistenceResult(inserted=inserted, reused=reused)


class PostgresFileFactReader:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def get_file_churn(self, repository_id: str) -> list[FileChurnRecord]:
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                """
                SELECT
                    file_path,
                    COUNT(DISTINCT commit_sha) AS commit_count,
                    SUM(insertions)            AS total_insertions,
                    SUM(deletions)             AS total_deletions
                FROM file_facts
                WHERE repository_id = %s
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
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                """
                SELECT f.file_path, c.sha
                FROM file_facts f
                JOIN commit_facts c ON c.sha = f.commit_sha AND c.repository_id = f.repository_id
                WHERE f.repository_id = %s
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
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                """
                SELECT
                    ff.file_path,
                    COUNT(DISTINCT cf.author_name) AS author_count,
                    COUNT(DISTINCT ff.commit_sha)  AS commit_count
                FROM file_facts ff
                JOIN commit_facts cf
                  ON ff.repository_id = cf.repository_id AND ff.commit_sha = cf.sha
                WHERE ff.repository_id = %s
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
