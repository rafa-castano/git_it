import psycopg

from git_it.repository_ingestion.application.ports import RepositoryRecord
from git_it.repository_ingestion.infrastructure.postgres._common import initialize


class PostgresRepositoryListReader:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def list_repositories(self) -> list[RepositoryRecord]:
        initialize(self._conninfo)
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                """
                SELECT
                    ir.repository_id,
                    ir.canonical_url,
                    ir.status,
                    (SELECT COUNT(*) FROM commit_facts cf
                        WHERE cf.repository_id = ir.repository_id) AS commit_count,
                    (SELECT COUNT(*) FROM commit_analyses ca
                        WHERE ca.repository_id = ir.repository_id) AS analysis_count,
                    EXISTS(SELECT 1 FROM case_studies cs
                        WHERE cs.repository_id = ir.repository_id) AS has_case_study
                FROM ingestion_runs ir
                GROUP BY ir.repository_id, ir.canonical_url, ir.status
                ORDER BY ir.repository_id
                """
            ).fetchall()
        return [
            RepositoryRecord(
                repository_id=str(row[0]),
                canonical_url=str(row[1]),
                status=str(row[2]),
                commit_count=int(row[3]),
                analysis_count=int(row[4]),
                has_case_study=bool(row[5]),
            )
            for row in rows
        ]


class PostgresRepositoryDeleter:
    """Hard-deletes all data for a repository from every table that holds its data.

    Deletes child tables first, then the parent ``ingestion_runs`` table, mirroring
    SqliteRepositoryDeleter. Tables absent from the schema are skipped, so deletion
    works even against a database provisioned by an older migration.
    """

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def delete_repository(self, repository_id: str) -> None:
        with psycopg.connect(self._conninfo) as conn:
            existing_tables = {
                row[0]
                for row in conn.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                ).fetchall()
            }
            # Child tables first (mirrors the SQLite deleter's dependency order)
            for table in (
                "github_context",
                "file_facts",
                "commit_analyses",
                "commit_facts",
                "case_studies",
                "repository_synopsis",
                "repo_metadata",
                "default_branch_metadata",
                "repository_files",
                "project_docs",
                "discussion_evidence",
                "embedding_vectors",
                "release_evidence",
                "advisory_evidence",
                "ingestion_runs",
            ):
                if table in existing_tables:
                    conn.execute(
                        f"DELETE FROM {table} WHERE repository_id = %s",  # noqa: S608
                        (repository_id,),
                    )
            conn.commit()
