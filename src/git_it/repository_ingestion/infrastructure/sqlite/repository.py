import sqlite3
from pathlib import Path

from git_it.repository_ingestion.application.ports import RepositoryRecord


class SqliteRepositoryListReader:
    """Read-side adapter: returns summary rows for all ingested repositories."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def list_repositories(self) -> list[RepositoryRecord]:
        # Scalar subqueries, not JOINs: commit_facts and commit_analyses are both
        # "many" tables keyed on repository_id. LEFT JOINing both onto the same
        # parent row produces their cross product per repository (fan-out) before
        # COUNT(DISTINCT ...) collapses it back down — correct but O(commits *
        # analyses) instead of O(commits + analyses). Verified ~1855ms -> ~0.1ms
        # on a repo with 1548 commits / 231 analyses.
        with sqlite3.connect(self._database_path) as conn:
            rows = conn.execute(
                """
                SELECT
                    ir.repository_id,
                    ir.canonical_url,
                    ir.status,
                    (SELECT COUNT(*) FROM commit_facts cf
                        WHERE cf.repository_id = ir.repository_id)     AS commit_count,
                    (SELECT COUNT(*) FROM commit_analyses ca
                        WHERE ca.repository_id = ir.repository_id)     AS analysis_count,
                    EXISTS(SELECT 1 FROM case_studies cs
                        WHERE cs.repository_id = ir.repository_id)     AS has_case_study
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


class SqliteRepositoryDeleter:
    """Hard-deletes all data for a repository from every table that holds its data.

    Deletes child tables first, then the parent ``ingestion_runs`` table, to respect
    logical dependency order (SQLite does not enforce FK constraints by default, but
    the order makes the intent explicit and safe for any future FK enforcement).
    """

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def delete_repository(self, repository_id: str) -> None:
        with sqlite3.connect(self._database_path) as conn:
            existing_tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            # Child tables first (optional tables are created lazily — skip if absent)
            for table in (
                "github_context",
                "file_facts",
                "commit_analyses",
                "commit_facts",
                "case_studies",
                "repository_synopsis",
                "repo_metadata",
                "default_branch_metadata",
                "project_docs",
                "release_evidence",
                "advisory_evidence",
                "ingestion_runs",
            ):
                if table in existing_tables:
                    conn.execute(
                        f"DELETE FROM {table} WHERE repository_id = ?",  # noqa: S608
                        (repository_id,),
                    )
