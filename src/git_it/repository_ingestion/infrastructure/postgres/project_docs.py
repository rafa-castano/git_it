"""PostgreSQL store for captured README/CHANGELOG excerpts (spec 025).

Mirrors ``SqliteProjectDocStore`` — see that module's docstring for why this
lives in its own dedicated module rather than alongside the GitHub-derived
stores in ``github.py``. Schema is provisioned via
``migrations/001_initial.sql`` only (applied separately via ``initialize()``
in ``_common.py``) — no ``initialize()`` method on this class itself, mirroring
``PostgresDefaultBranchStore``.
"""

from datetime import datetime

import psycopg

from git_it.repository_ingestion.domain.project_docs import ProjectDocContent


class PostgresProjectDocStore:
    """Persists one upserted README/CHANGELOG excerpt row per repository (PostgreSQL, spec 025).

    Mirrors ``SqliteProjectDocStore`` — see that class's docstring for the
    independent-table rationale (shared with spec 020's default-branch store).
    """

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def save_project_docs(self, content: ProjectDocContent) -> None:
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                """
                INSERT INTO project_docs (
                    repository_id, readme_text, readme_truncated,
                    changelog_text, changelog_truncated, captured_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (repository_id) DO UPDATE SET
                    readme_text         = EXCLUDED.readme_text,
                    readme_truncated    = EXCLUDED.readme_truncated,
                    changelog_text      = EXCLUDED.changelog_text,
                    changelog_truncated = EXCLUDED.changelog_truncated,
                    captured_at         = EXCLUDED.captured_at
                """,
                (
                    content.repository_id,
                    content.readme_text,
                    1 if content.readme_truncated else 0,
                    content.changelog_text,
                    1 if content.changelog_truncated else 0,
                    content.captured_at.isoformat(),
                ),
            )
            conn.commit()

    def get_project_docs(self, repository_id: str) -> ProjectDocContent | None:
        with psycopg.connect(self._conninfo) as conn:
            row = conn.execute(
                """
                SELECT readme_text, readme_truncated, changelog_text,
                       changelog_truncated, captured_at
                FROM project_docs
                WHERE repository_id = %s
                """,
                (repository_id,),
            ).fetchone()
        if row is None:
            return None
        return ProjectDocContent(
            repository_id=repository_id,
            readme_text=str(row[0]) if row[0] is not None else None,
            readme_truncated=bool(row[1]),
            changelog_text=str(row[2]) if row[2] is not None else None,
            changelog_truncated=bool(row[3]),
            captured_at=datetime.fromisoformat(str(row[4])),
        )
