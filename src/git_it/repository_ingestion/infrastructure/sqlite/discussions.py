import json
import sqlite3
from datetime import datetime
from pathlib import Path

from git_it.repository_ingestion.domain.discussions import DiscussionEvidence


class SqliteDiscussionEvidenceStore:
    """Persists LLM-summarized, schema-validated discussion evidence (spec 022).

    One row per ``(repository_id, discussion_id)``, upserted. Raw discussion text
    (``Discussion.title``/``body``/``answer_body``) never reaches this store — only the
    validated ``DiscussionEvidence`` output does. A missing repository_id simply means
    "no qualifying discussions were summarized for this repository" (no token, non-GitHub
    URL, zero qualifying discussions, or a pre-existing repository ingested before this
    feature shipped) — mirroring the "missing row" contract already used by
    ``SqliteRepoMetadataStore``.
    """

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._database_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS discussion_evidence (
                    repository_id  TEXT NOT NULL,
                    discussion_id  TEXT NOT NULL,
                    discussion_url TEXT NOT NULL,
                    claim_type     TEXT NOT NULL,
                    summary        TEXT NOT NULL,
                    confidence     REAL NOT NULL,
                    limitations    TEXT NOT NULL DEFAULT '[]',
                    source_inputs  TEXT NOT NULL DEFAULT '[]',
                    generated_at   TEXT NOT NULL,
                    model          TEXT NOT NULL,
                    PRIMARY KEY (repository_id, discussion_id)
                )
                """
            )
            conn.commit()

    def save_discussion_evidence(self, repository_id: str, items: list[DiscussionEvidence]) -> None:
        with sqlite3.connect(self._database_path) as conn:
            for item in items:
                conn.execute(
                    """
                    INSERT INTO discussion_evidence (
                        repository_id, discussion_id, discussion_url, claim_type,
                        summary, confidence, limitations, source_inputs,
                        generated_at, model
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(repository_id, discussion_id) DO UPDATE SET
                        discussion_url = excluded.discussion_url,
                        claim_type     = excluded.claim_type,
                        summary        = excluded.summary,
                        confidence     = excluded.confidence,
                        limitations    = excluded.limitations,
                        source_inputs  = excluded.source_inputs,
                        generated_at   = excluded.generated_at,
                        model          = excluded.model
                    """,
                    (
                        repository_id,
                        item.discussion_id,
                        item.discussion_url,
                        item.claim_type,
                        item.summary,
                        item.confidence,
                        json.dumps(item.limitations),
                        json.dumps(item.source_inputs),
                        item.generated_at.isoformat(),
                        item.model,
                    ),
                )
            conn.commit()

    def get_discussion_evidence(self, repository_id: str) -> list[DiscussionEvidence]:
        with sqlite3.connect(self._database_path) as conn:
            rows = conn.execute(
                """
                SELECT discussion_id, discussion_url, claim_type, summary, confidence,
                       limitations, source_inputs, generated_at, model
                FROM discussion_evidence
                WHERE repository_id = ?
                """,
                (repository_id,),
            ).fetchall()
        return [
            DiscussionEvidence(
                discussion_id=str(row[0]),
                discussion_url=str(row[1]),
                claim_type=str(row[2]),  # type: ignore[arg-type]
                summary=str(row[3]),
                confidence=float(row[4]),
                limitations=json.loads(str(row[5])),
                source_inputs=json.loads(str(row[6])),
                generated_at=datetime.fromisoformat(str(row[7])),
                model=str(row[8]),
            )
            for row in rows
        ]
