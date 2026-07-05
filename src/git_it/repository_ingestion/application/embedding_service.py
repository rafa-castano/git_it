"""Per-item embedding computation for spec 023 (RAG-Enhanced Semantic Search).

``EmbeddingService`` is the application-layer boundary between an already-validated
``CommitAnalysis``/``DiscussionEvidence`` and a persisted ``EmbeddedChunk``. It mirrors
``DiscussionSummarizer``'s per-item failure isolation posture (spec 022, batch 109): each
call to the underlying ``EmbeddingClient`` is wrapped so that a single item's embedding
failure (rate limit, network error, malformed response) never propagates to the caller —
it simply returns ``None`` for that one item, leaving the surrounding analysis/
summarization batch unaffected.

Only already-validated summary text is ever passed to ``EmbeddingClient.embed()`` — never
raw commit/diff content or raw ``Discussion`` fields (spec 023 Non-goals). Two locked
implementation decisions from spec 023 (documented in the batch-120 progress doc):

1. Only ``CommitAnalysis.summary`` is embedded, never ``summary_beginner``/``summary_expert``.
2. For discussion evidence, ``EmbeddedChunk.source_id`` holds the full, citation-ready
   ``DiscussionEvidence.discussion_url`` — not the bare ``discussion_id``.
"""

import logging
from datetime import UTC, datetime

from git_it.repository_ingestion.application.ports import EmbeddingClient
from git_it.repository_ingestion.domain.analysis import CommitAnalysis
from git_it.repository_ingestion.domain.discussions import DiscussionEvidence
from git_it.repository_ingestion.domain.embeddings import EmbeddedChunk

_logger = logging.getLogger(__name__)

_UNKNOWN_MODEL = "unknown"


class EmbeddingService:
    """Computes and wraps embeddings for commit analyses and discussion evidence."""

    def __init__(self, embedding_client: EmbeddingClient) -> None:
        self._embedding_client = embedding_client

    def embed_commit_analysis(
        self, repository_id: str, analysis: CommitAnalysis
    ) -> EmbeddedChunk | None:
        return self._embed(
            repository_id=repository_id,
            source_type="commit_analysis",
            source_id=analysis.commit_sha,
            text=analysis.summary,
        )

    def embed_discussion_evidence(
        self, repository_id: str, evidence: DiscussionEvidence
    ) -> EmbeddedChunk | None:
        return self._embed(
            repository_id=repository_id,
            source_type="discussion_evidence",
            # Locked decision: the citation-ready evidence reference (the full URL),
            # not the bare discussion_id -- see module docstring.
            source_id=evidence.discussion_url,
            text=evidence.summary,
        )

    def _embed(
        self,
        *,
        repository_id: str,
        source_type: str,
        source_id: str,
        text: str,
    ) -> EmbeddedChunk | None:
        try:
            vector = self._embedding_client.embed(text)
            return EmbeddedChunk(
                repository_id=repository_id,
                source_type=source_type,  # type: ignore[arg-type]
                source_id=source_id,
                text=text,
                vector=vector,
                model=getattr(self._embedding_client, "_model", _UNKNOWN_MODEL),
                created_at=datetime.now(UTC),
            )
        except Exception as exc:  # noqa: BLE001 - one item's embedding failure must not abort the batch
            _logger.warning("embedding failed: %s", type(exc).__name__)
            return None
