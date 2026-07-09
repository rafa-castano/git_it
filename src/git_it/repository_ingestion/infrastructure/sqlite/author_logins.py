"""SQLite adapter for the per-repository author-email -> GitHub-login mapping (spec 031)."""

import sqlite3
from pathlib import Path


class SqliteAuthorLoginStore:
    """Persists ``author_email -> github_login | null`` per repository (spec 031).

    A stored ``NULL`` ``github_login`` is an "attempted, no match" marker so that
    email is never re-queried against the GitHub API on a later ingest. A missing
    row means "never attempted". Upsert (INSERT ... ON CONFLICT) makes re-saving
    idempotent — a later run that resolves a previously-null email overwrites the
    marker with the login.
    """

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._database_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS author_logins (
                    repository_id TEXT NOT NULL,
                    author_email  TEXT NOT NULL,
                    github_login  TEXT,
                    updated_at    TEXT NOT NULL,
                    PRIMARY KEY (repository_id, author_email)
                )
                """
            )
            conn.commit()

    def save_author_logins(self, repository_id: str, mapping: dict[str, str | None]) -> None:
        with sqlite3.connect(self._database_path) as conn:
            conn.executemany(
                """
                INSERT INTO author_logins (repository_id, author_email, github_login, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(repository_id, author_email) DO UPDATE SET
                    github_login = excluded.github_login,
                    updated_at   = excluded.updated_at
                """,
                [(repository_id, email, login) for email, login in mapping.items()],
            )
            conn.commit()

    def get_author_logins(self, repository_id: str) -> dict[str, str | None]:
        with sqlite3.connect(self._database_path) as conn:
            rows = conn.execute(
                "SELECT author_email, github_login FROM author_logins WHERE repository_id = ?",
                (repository_id,),
            ).fetchall()
        return {str(row[0]): (str(row[1]) if row[1] is not None else None) for row in rows}

    def read_distinct_author_emails(self, repository_id: str) -> set[str]:
        """Return the distinct non-empty ``author_email`` values in ``commit_facts``.

        Convenience for the spec 031 enrichment hook, which computes the needed set
        as ``distinct_emails - already_attempted``. Lives here (rather than on a
        separate reader) so the hook depends on a single collaborator besides the
        fetcher. Returns an empty set for an unknown repository.
        """
        with sqlite3.connect(self._database_path) as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT author_email FROM commit_facts
                WHERE repository_id = ? AND author_email != ''
                """,
                (repository_id,),
            ).fetchall()
        return {str(row[0]) for row in rows}
