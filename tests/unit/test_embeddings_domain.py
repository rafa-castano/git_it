"""Tests for the embeddings domain model (spec 023) — EmbeddedChunk.

EmbeddedChunk is a plain frozen dataclass (not Pydantic) — an internal,
backend-agnostic persistence shape for an already-computed embedding vector,
not an LLM-output-validation boundary like DiscussionEvidence/CommitAnalysis.
"""

from datetime import UTC, datetime

from git_it.repository_ingestion.domain.embeddings import EmbeddedChunk


def test_embedded_chunk_constructs_with_commit_analysis_source_type() -> None:
    chunk = EmbeddedChunk(
        repository_id="repo-1",
        source_type="commit_analysis",
        source_id="abc123",
        text="Added a new feature to the login flow.",
        vector=[0.1, 0.2, 0.3],
        model="text-embedding-3-small",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert chunk.repository_id == "repo-1"
    assert chunk.source_type == "commit_analysis"
    assert chunk.source_id == "abc123"
    assert chunk.text == "Added a new feature to the login flow."
    assert chunk.vector == [0.1, 0.2, 0.3]
    assert chunk.model == "text-embedding-3-small"
    assert chunk.created_at == datetime(2026, 1, 1, tzinfo=UTC)


def test_embedded_chunk_constructs_with_discussion_evidence_source_type() -> None:
    chunk = EmbeddedChunk(
        repository_id="repo-1",
        source_type="discussion_evidence",
        source_id="d-1",
        text="The team chose approach X over Y for performance reasons.",
        vector=[0.4, 0.5, 0.6],
        model="text-embedding-3-small",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert chunk.source_type == "discussion_evidence"
    assert chunk.source_id == "d-1"
