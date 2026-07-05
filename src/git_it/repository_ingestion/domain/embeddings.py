"""Domain concepts for embedding-based semantic search (spec 023).

``EmbeddedChunk`` is the persisted, backend-agnostic embedding record: a vector
computed from an already-validated ``CommitAnalysis``/``DiscussionEvidence``
summary, keyed to the commit or discussion it describes. Unlike
``DiscussionEvidence`` (a Pydantic model that validates untrusted LLM output at
a schema boundary), this is a plain frozen dataclass — there is no LLM output to
validate here, only an internal persistence shape for a vector this codebase
computed itself. It does, however, get persisted (one row per
``(repository_id, source_type, source_id)``, see ``SqliteEmbeddingStore`` /
``PostgresEmbeddingStore``), unlike the raw, never-persisted ``Discussion``
dataclass in ``domain/discussions.py``.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class EmbeddedChunk:
    """A single persisted embedding vector for one already-validated summary."""

    repository_id: str
    source_type: Literal["commit_analysis", "discussion_evidence"]
    source_id: str
    text: str
    vector: list[float]
    model: str
    created_at: datetime
