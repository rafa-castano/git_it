"""PostgreSQL adapter for the per-repository author-email -> GitHub-login mapping (spec 031).

Mirrors ``SqliteAuthorLoginStore``. The ``author_logins`` table is created by
``migrations/001_initial.sql`` (run via ``initialize``), so this adapter has no
``initialize`` of its own — consistent with the other Postgres stores.
"""

import psycopg


class PostgresAuthorLoginStore:
    """Persists ``author_email -> github_login | null`` per repository (PostgreSQL, spec 031)."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def save_author_logins(self, repository_id: str, mapping: dict[str, str | None]) -> None:
        with psycopg.connect(self._conninfo) as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO author_logins
                        (repository_id, author_email, github_login, updated_at)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (repository_id, author_email) DO UPDATE SET
                        github_login = EXCLUDED.github_login,
                        updated_at   = EXCLUDED.updated_at
                    """,
                    [(repository_id, email, login) for email, login in mapping.items()],
                )
            conn.commit()

    def get_author_logins(self, repository_id: str) -> dict[str, str | None]:
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                "SELECT author_email, github_login FROM author_logins WHERE repository_id = %s",
                (repository_id,),
            ).fetchall()
        return {str(row[0]): (str(row[1]) if row[1] is not None else None) for row in rows}

    def read_distinct_author_emails(self, repository_id: str) -> set[str]:
        """Return the distinct non-empty ``author_email`` values in ``commit_facts``.

        Convenience for the spec 031 enrichment hook (see ``SqliteAuthorLoginStore``).
        """
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT author_email FROM commit_facts
                WHERE repository_id = %s AND author_email != ''
                """,
                (repository_id,),
            ).fetchall()
        return {str(row[0]) for row in rows}
