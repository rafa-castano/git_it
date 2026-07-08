import psycopg


class PostgresFileTreeStore:
    """Persists the set of tracked file paths per repository (PostgreSQL, spec 029).

    Mirrors ``SqliteFileTreeStore`` — replace-on-write per repository (a file
    tree is a snapshot, not a log): delete the repository's existing rows, then
    insert the new set in one transaction. The ``repository_files`` table is
    provisioned by ``migrations/001_initial.sql`` (run via ``initialize``), so
    this store has no ``initialize`` method of its own.
    """

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def save_file_paths(self, repository_id: str, paths: list[str]) -> None:
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                "DELETE FROM repository_files WHERE repository_id = %s",
                (repository_id,),
            )
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO repository_files (repository_id, path) VALUES (%s, %s)"
                    " ON CONFLICT (repository_id, path) DO NOTHING",
                    [(repository_id, path) for path in paths],
                )
            conn.commit()

    def get_file_paths(self, repository_id: str) -> list[str]:
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                "SELECT path FROM repository_files WHERE repository_id = %s ORDER BY path",
                (repository_id,),
            ).fetchall()
        return [str(row[0]) for row in rows]
