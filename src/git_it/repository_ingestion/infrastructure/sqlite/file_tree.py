import sqlite3
from pathlib import Path


class SqliteFileTreeStore:
    """Persists the set of tracked file paths per repository (spec 029, slice 1).

    A repository's file tree is a snapshot, not an accumulating log, so
    ``save_file_paths`` is replace-on-write: it deletes the repository's
    existing rows and inserts the new set in one transaction. A missing set
    means "not yet captured" (pre-existing repository ingested before this
    feature, or refreshed after) — ``get_file_paths`` then returns ``[]`` and
    the frontend simply renders no verified file links.

    Deliberately a new, independent table (``repository_files``) from spec 020's
    ``default_branch_metadata`` — see spec 029 §8: keeping each capture's
    contract independent and reversible.
    """

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._database_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS repository_files (
                    repository_id TEXT NOT NULL,
                    path          TEXT NOT NULL,
                    PRIMARY KEY (repository_id, path)
                )
                """
            )
            conn.commit()

    def save_file_paths(self, repository_id: str, paths: list[str]) -> None:
        with sqlite3.connect(self._database_path) as conn:
            conn.execute(
                "DELETE FROM repository_files WHERE repository_id = ?",
                (repository_id,),
            )
            conn.executemany(
                "INSERT OR IGNORE INTO repository_files (repository_id, path) VALUES (?, ?)",
                [(repository_id, path) for path in paths],
            )
            conn.commit()

    def get_file_paths(self, repository_id: str) -> list[str]:
        with sqlite3.connect(self._database_path) as conn:
            rows = conn.execute(
                "SELECT path FROM repository_files WHERE repository_id = ? ORDER BY path",
                (repository_id,),
            ).fetchall()
        return [str(row[0]) for row in rows]
