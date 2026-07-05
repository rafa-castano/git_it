"""RAG-enhanced semantic search over persisted embeddings (spec 023).

``SemanticSearchService`` is the application-layer boundary that turns a natural-language
query into a ranked list of evidence-linked ``SimilarityResult`` items. It embeds the query
via the same ``EmbeddingClient`` used at ingestion time, loads every persisted
``EmbeddedChunk`` for the repository via ``EmbeddingReader``, and computes cosine similarity
between the query vector and every stored vector in pure Python -- no numpy, no ANN index.
At this project's realistic scale (hundreds to low thousands of short vectors per
repository), a linear scan is a sub-millisecond-to-low-millisecond operation (spec 023 Goals).

Locked simplification (orchestrator-directed, batch 121): spec 023 originally described
``SimilarityResult`` with 5 fields, including both ``source_id`` and ``evidence_ref``. Since
batch 120 already made ``EmbeddedChunk.source_id`` hold the full citation-ready evidence
reference directly (the ``commit_sha`` or the full ``discussion_url``), carrying both
``source_id`` and ``evidence_ref`` on ``SimilarityResult`` would just duplicate the same
value twice. ``SimilarityResult`` therefore has 4 fields, not 5: ``source_type``,
``evidence_ref`` (== the matched chunk's ``source_id``), ``summary_text`` (== the matched
chunk's ``text``), and ``score``.
"""

import math
from dataclasses import dataclass

from git_it.repository_ingestion.application.ports import EmbeddingClient, EmbeddingReader

DEFAULT_TOP_K = 10


@dataclass(frozen=True)
class SimilarityResult:
    """One ranked semantic-search match, evidence-linked back to its source."""

    source_type: str
    evidence_ref: str
    summary_text: str
    score: float


class SemanticSearchService:
    """Embeds a query and ranks the repository's stored embeddings by cosine similarity."""

    def __init__(
        self,
        embedding_client: EmbeddingClient,
        embedding_reader: EmbeddingReader,
    ) -> None:
        self._embedding_client = embedding_client
        self._embedding_reader = embedding_reader

    def search(
        self, repository_id: str, query: str, top_k: int = DEFAULT_TOP_K
    ) -> list[SimilarityResult]:
        if not query.strip():
            raise ValueError("query must not be empty")

        query_vector = self._embedding_client.embed(query)

        chunks = self._embedding_reader.get_all_embeddings(repository_id)
        if not chunks:
            return []

        scored = [(self._cosine_similarity(query_vector, chunk.vector), chunk) for chunk in chunks]
        scored.sort(key=lambda pair: pair[0], reverse=True)

        return [
            SimilarityResult(
                source_type=chunk.source_type,
                evidence_ref=chunk.source_id,
                summary_text=chunk.text,
                score=score,
            )
            for score, chunk in scored[:top_k]
        ]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b, strict=True))
        return dot / (norm_a * norm_b)
