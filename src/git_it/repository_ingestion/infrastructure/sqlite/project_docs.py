"""SQLite store for captured README/CHANGELOG excerpts (spec 025).

Lives in its own dedicated module rather than alongside the GitHub-derived
stores in ``github.py``: unlike ``SqliteDefaultBranchStore`` (which ended up
in ``github.py`` for file-layout reasons at the time it was built, even
though its own capture mechanism is git-based, not GitHub-API-based),
project-doc content has nothing to do with GitHub's API either, so it gets
its own module — mirroring the same reasoning ``GitPythonProjectDocReader``
already used (batch 130) for its own dedicated ``infrastructure/project_docs.py``.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

from git_it.repository_ingestion.domain.project_docs import ProjectDocContent


class SqliteProjectDocStore:
    """Persists one upserted README/CHANGELOG excerpt row per repository (spec 025).

    Independent table from ``default_branch_metadata`` and ``repo_metadata`` —
    same rationale spec 020 already used: different capture trigger, no
    token-gating, avoid loosening an unrelated already-shipped contract. A
    missing row means "not yet captured" (pre-existing repository, or neither
    file was found at ingestion time) — the narrative prompt simply omits the
    "## Project Documentation" section for that repository.
    """

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._database_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS project_docs (
                    repository_id      TEXT PRIMARY KEY,
                    readme_text        TEXT,
                    readme_truncated   INTEGER NOT NULL DEFAULT 0,
                    changelog_text     TEXT,
                    changelog_truncated INTEGER NOT NULL DEFAULT 0,
                    captured_at        TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def save_project_docs(self, content: ProjectDocContent) -> None:
        with sqlite3.connect(self._database_path) as conn:
            conn.execute(
                """
                INSERT INTO project_docs (
                    repository_id, readme_text, readme_truncated,
                    changelog_text, changelog_truncated, captured_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(repository_id) DO UPDATE SET
                    readme_text         = excluded.readme_text,
                    readme_truncated    = excluded.readme_truncated,
                    changelog_text      = excluded.changelog_text,
                    changelog_truncated = excluded.changelog_truncated,
                    captured_at         = excluded.captured_at
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
        with sqlite3.connect(self._database_path) as conn:
            row = conn.execute(
                """
                SELECT readme_text, readme_truncated, changelog_text,
                       changelog_truncated, captured_at
                FROM project_docs
                WHERE repository_id = ?
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
