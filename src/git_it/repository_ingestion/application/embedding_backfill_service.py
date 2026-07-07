"""Embedding backfill for already-stored evidence (spec 027, slice 1).

Embeddings are normally computed *live*, inline with analysis (``CommitAnalysisService``)
or discussion ingest (``api/routes/repos.py``). Anything analyzed before
``OPENAI_API_KEY`` was configured has a persisted ``CommitAnalysis``/``DiscussionEvidence``
row but no matching ``EmbeddedChunk`` -- nothing ever fills that gap on its own.

``EmbeddingBackfillService`` closes it: it enumerates already-stored commit analyses and
discussion evidence, computes the subset whose ``(source_type, source_id)`` is absent from
``EmbeddingReader.get_all_embeddings``, and embeds only that missing subset through the
same embedder shape ``EmbeddingService`` already implements. The embedding store's PK
``(repository_id, source_type, source_id)`` upserts, so re-running after a completed
backfill is a no-op -- see ``test_second_backfill_run_is_idempotent_and_embeds_nothing``.

Per-item failure isolation mirrors ``EmbeddingService._embed`` exactly: one item's
embedding failure is caught, logged by ``type(exc).__name__`` only (never the raw
exception or the text being embedded), and skipped -- it never aborts the batch. This is
applied at this layer too (not merely inherited from ``EmbeddingService``), because the
embedder this service depends on is a Protocol, not necessarily the concrete
``EmbeddingService`` -- any embedder that raises instead of returning ``None`` must still
be isolated per-item here.

A ``None`` embedder (mirrors ``build_embedding_client()`` returning ``None`` without
``OPENAI_API_KEY``) makes this service a clean no-op -- see ``build_embedding_backfill_service``
in ``composition.py``.
"""

import logging
from dataclasses import dataclass
from typing import Protocol

from git_it.repository_ingestion.application.ports import (
    CommitAnalysisReader,
    DiscussionEvidenceReader,
    EmbeddingReader,
    EmbeddingWriter,
)
from git_it.repository_ingestion.domain.analysis import CommitAnalysis
from git_it.repository_ingestion.domain.discussions import DiscussionEvidence
from git_it.repository_ingestion.domain.embeddings import EmbeddedChunk

_logger = logging.getLogger(__name__)


class BackfillEmbedder(Protocol):
    """Computes embeddings for both evidence types the live pipeline embeds (spec 023).

    Mirrors ``EmbeddingService``'s two public methods structurally, so this service
    depends on the shape it needs rather than importing the concrete class --
    consistent with the hexagonal boundary the rest of this module keeps.
    ``EmbeddingService`` satisfies this Protocol without any changes.
    """

    def embed_commit_analysis(
        self, repository_id: str, analysis: CommitAnalysis
    ) -> EmbeddedChunk | None: ...

    def embed_discussion_evidence(
        self, repository_id: str, evidence: DiscussionEvidence
    ) -> EmbeddedChunk | None: ...


@dataclass(frozen=True)
class EmbeddingBackfillResult:
    """Outcome counts from one ``EmbeddingBackfillService.backfill()`` call."""

    embedded: int
    already_present: int
    failed: int


_NO_OP_RESULT = EmbeddingBackfillResult(embedded=0, already_present=0, failed=0)


class EmbeddingBackfillService:
    """Backfills embeddings for already-stored evidence missing one (spec 027)."""

    def __init__(
        self,
        *,
        commit_analysis_reader: CommitAnalysisReader,
        discussion_evidence_reader: DiscussionEvidenceReader,
        embedding_reader: EmbeddingReader,
        embedding_writer: EmbeddingWriter,
        embedder: BackfillEmbedder | None,
    ) -> None:
        self._commit_analysis_reader = commit_analysis_reader
        self._discussion_evidence_reader = discussion_evidence_reader
        self._embedding_reader = embedding_reader
        self._embedding_writer = embedding_writer
        self._embedder = embedder

    @property
    def is_available(self) -> bool:
        """True when an embedder is configured (i.e. ``OPENAI_API_KEY`` is set).

        Callers use this to distinguish "backfill is unavailable (no key)" from
        "nothing to backfill (all evidence already embedded)" -- both otherwise yield a
        zero ``estimate_backfill_calls`` and are indistinguishable to a caller.
        """
        return self._embedder is not None

    def estimate_backfill_calls(self, repository_id: str) -> int:
        """Count already-stored items lacking a persisted embedding.

        Feeds the budget guardrail (batch 38) in a later batch, mirroring the *shape*
        of ``CommitAnalysisService.estimate_llm_calls`` -- a different quantity
        (unanalyzed commits vs. analyzed-but-unembedded items), same purpose. Returns 0
        without an embedder: nothing could be backfilled either way.
        """
        if self._embedder is None:
            return 0
        missing_analyses, missing_evidence, _ = self._missing_items(repository_id)
        return len(missing_analyses) + len(missing_evidence)

    def backfill(self, repository_id: str) -> EmbeddingBackfillResult:
        """Embed every already-stored item missing an embedding, persist, and report counts.

        Idempotent: a second call after a completed run finds nothing missing and embeds
        zero items. Never raises on a per-item embedding failure -- see module docstring.
        """
        if self._embedder is None:
            return _NO_OP_RESULT

        missing_analyses, missing_evidence, already_present = self._missing_items(repository_id)

        embedded_chunks: list[EmbeddedChunk] = []
        failed = 0

        for analysis in missing_analyses:
            chunk = self._safe_embed_commit_analysis(repository_id, analysis)
            if chunk is None:
                failed += 1
                continue
            embedded_chunks.append(chunk)

        for item in missing_evidence:
            chunk = self._safe_embed_discussion_evidence(repository_id, item)
            if chunk is None:
                failed += 1
                continue
            embedded_chunks.append(chunk)

        if embedded_chunks:
            self._embedding_writer.save_embeddings(repository_id, embedded_chunks)

        return EmbeddingBackfillResult(
            embedded=len(embedded_chunks),
            already_present=already_present,
            failed=failed,
        )

    def _missing_items(
        self, repository_id: str
    ) -> tuple[list[CommitAnalysis], list[DiscussionEvidence], int]:
        """Return (missing analyses, missing evidence, count already embedded)."""
        existing_keys = self._existing_keys(repository_id)
        analyses = self._commit_analysis_reader.list_analyses(repository_id, limit=None)
        evidence = self._discussion_evidence_reader.get_discussion_evidence(repository_id)
        missing_analyses = [
            analysis
            for analysis in analyses
            if ("commit_analysis", analysis.commit_sha) not in existing_keys
        ]
        missing_evidence = [
            item
            for item in evidence
            if ("discussion_evidence", item.discussion_url) not in existing_keys
        ]
        already_present = (len(analyses) - len(missing_analyses)) + (
            len(evidence) - len(missing_evidence)
        )
        return missing_analyses, missing_evidence, already_present

    def _existing_keys(self, repository_id: str) -> set[tuple[str, str]]:
        return {
            (chunk.source_type, chunk.source_id)
            for chunk in self._embedding_reader.get_all_embeddings(repository_id)
        }

    def _safe_embed_commit_analysis(
        self, repository_id: str, analysis: CommitAnalysis
    ) -> EmbeddedChunk | None:
        assert self._embedder is not None  # narrowed by backfill()'s early return
        try:
            return self._embedder.embed_commit_analysis(repository_id, analysis)
        except Exception as exc:  # noqa: BLE001 - one item's failure must not abort the batch
            _logger.warning("embedding backfill failed: %s", type(exc).__name__)
            return None

    def _safe_embed_discussion_evidence(
        self, repository_id: str, evidence: DiscussionEvidence
    ) -> EmbeddedChunk | None:
        assert self._embedder is not None  # narrowed by backfill()'s early return
        try:
            return self._embedder.embed_discussion_evidence(repository_id, evidence)
        except Exception as exc:  # noqa: BLE001 - one item's failure must not abort the batch
            _logger.warning("embedding backfill failed: %s", type(exc).__name__)
            return None
