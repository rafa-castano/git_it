from datetime import UTC, datetime

import pytest

from git_it.repository_ingestion.application.embedding_backfill_service import (
    EmbeddingBackfillService,
)
from git_it.repository_ingestion.domain.analysis import CommitAnalysis, CommitCategory
from git_it.repository_ingestion.domain.discussions import DiscussionEvidence
from git_it.repository_ingestion.domain.embeddings import EmbeddedChunk


def _make_analysis(
    *,
    commit_sha: str = "abc123",
    summary: str = "Fixed a SQL injection vulnerability in the login form.",
) -> CommitAnalysis:
    return CommitAnalysis(
        commit_sha=commit_sha,
        summary=summary,
        summary_beginner="Beginner variant text.",
        summary_expert="Expert variant text.",
        category=CommitCategory.SECURITY,
        confidence=0.9,
    )


def _make_evidence(
    *,
    discussion_id: str = "D_1",
    discussion_url: str = "https://github.com/owner/repo/discussions/1",
    summary: str = "We chose X for Y reasons.",
) -> DiscussionEvidence:
    return DiscussionEvidence(
        discussion_id=discussion_id,
        discussion_url=discussion_url,
        claim_type="design_rationale",
        summary=summary,
        confidence=0.8,
        limitations=[],
        source_inputs=[discussion_id],
        generated_at=datetime.now(UTC),
        model="fake-model",
    )


def _make_chunk(
    *,
    repository_id: str = "repo-1",
    source_type: str = "commit_analysis",
    source_id: str = "abc123",
    text: str = "some summary",
    vector: list[float] | None = None,
    model: str = "fake-embed-model",
) -> EmbeddedChunk:
    return EmbeddedChunk(
        repository_id=repository_id,
        source_type=source_type,  # type: ignore[arg-type]
        source_id=source_id,
        text=text,
        vector=vector if vector is not None else [0.1, 0.2],
        model=model,
        created_at=datetime.now(UTC),
    )


class _StubCommitAnalysisReader:
    """Fake CommitAnalysisReader keyed by repository_id, mirroring the real port shape."""

    def __init__(self, analyses_by_repo: dict[str, list[CommitAnalysis]]) -> None:
        self._analyses_by_repo = analyses_by_repo

    def get_analysis(self, *, repository_id: str, commit_sha: str) -> CommitAnalysis | None:
        raise NotImplementedError("EmbeddingBackfillService only calls list_analyses")

    def list_analyses(
        self, repository_id: str, *, limit: int | None = None
    ) -> list[CommitAnalysis]:
        return list(self._analyses_by_repo.get(repository_id, []))


class _StubDiscussionEvidenceReader:
    """Fake DiscussionEvidenceReader keyed by repository_id."""

    def __init__(self, evidence_by_repo: dict[str, list[DiscussionEvidence]]) -> None:
        self._evidence_by_repo = evidence_by_repo

    def get_discussion_evidence(self, repository_id: str) -> list[DiscussionEvidence]:
        return list(self._evidence_by_repo.get(repository_id, []))


class _FakeEmbeddingStore:
    """Fake combined EmbeddingReader/EmbeddingWriter with the real upsert PK semantics.

    Mirrors ``SqliteEmbeddingStore``'s ``(repository_id, source_type, source_id)`` upsert
    so idempotency can be exercised end-to-end against fakes only, no real DB.
    """

    def __init__(self, initial: list[EmbeddedChunk] | None = None) -> None:
        self._chunks: dict[tuple[str, str, str], EmbeddedChunk] = {
            (chunk.repository_id, chunk.source_type, chunk.source_id): chunk
            for chunk in (initial or [])
        }

    def get_all_embeddings(self, repository_id: str) -> list[EmbeddedChunk]:
        return [chunk for (rid, _, _), chunk in self._chunks.items() if rid == repository_id]

    def save_embeddings(self, repository_id: str, items: list[EmbeddedChunk]) -> None:
        for item in items:
            self._chunks[(repository_id, item.source_type, item.source_id)] = item


class _FakeEmbedder:
    """Fake embedder shaped like EmbeddingService, with scriptable per-item failures."""

    def __init__(
        self,
        *,
        commit_failures: set[str] | None = None,
        evidence_failures: set[str] | None = None,
    ) -> None:
        self.commit_calls: list[str] = []
        self.evidence_calls: list[str] = []
        self._commit_failures = commit_failures or set()
        self._evidence_failures = evidence_failures or set()

    def embed_commit_analysis(
        self, repository_id: str, analysis: CommitAnalysis
    ) -> EmbeddedChunk | None:
        self.commit_calls.append(analysis.commit_sha)
        if analysis.commit_sha in self._commit_failures:
            raise RuntimeError(f"embedding boom for {analysis.summary}")
        return _make_chunk(
            repository_id=repository_id,
            source_type="commit_analysis",
            source_id=analysis.commit_sha,
            text=analysis.summary,
        )

    def embed_discussion_evidence(
        self, repository_id: str, evidence: DiscussionEvidence
    ) -> EmbeddedChunk | None:
        self.evidence_calls.append(evidence.discussion_url)
        if evidence.discussion_url in self._evidence_failures:
            raise RuntimeError(f"embedding boom for {evidence.summary}")
        return _make_chunk(
            repository_id=repository_id,
            source_type="discussion_evidence",
            source_id=evidence.discussion_url,
            text=evidence.summary,
        )


def test_count_missing_counts_analyses_and_evidence_without_an_embedding() -> None:
    repo = "repo-1"
    analyses = [_make_analysis(commit_sha=f"sha{i}") for i in range(8)]
    evidence = [
        _make_evidence(
            discussion_id=f"D{i}",
            discussion_url=f"https://github.com/owner/repo/discussions/{i}",
        )
        for i in range(3)
    ]
    already_embedded = [
        _make_chunk(repository_id=repo, source_type="commit_analysis", source_id="sha0"),
        _make_chunk(repository_id=repo, source_type="commit_analysis", source_id="sha1"),
    ]
    store = _FakeEmbeddingStore(initial=already_embedded)
    service = EmbeddingBackfillService(
        commit_analysis_reader=_StubCommitAnalysisReader({repo: analyses}),
        discussion_evidence_reader=_StubDiscussionEvidenceReader({repo: evidence}),
        embedding_reader=store,
        embedding_writer=store,
        embedder=_FakeEmbedder(),
    )

    assert service.estimate_backfill_calls(repo) == 9


def test_backfill_embeds_only_items_missing_an_embedding() -> None:
    repo = "repo-1"
    analyses = [_make_analysis(commit_sha="sha1"), _make_analysis(commit_sha="sha2")]
    evidence = [_make_evidence(discussion_url="https://github.com/owner/repo/discussions/1")]
    store = _FakeEmbeddingStore(
        initial=[
            _make_chunk(repository_id=repo, source_type="commit_analysis", source_id="sha1"),
        ]
    )
    embedder = _FakeEmbedder()
    service = EmbeddingBackfillService(
        commit_analysis_reader=_StubCommitAnalysisReader({repo: analyses}),
        discussion_evidence_reader=_StubDiscussionEvidenceReader({repo: evidence}),
        embedding_reader=store,
        embedding_writer=store,
        embedder=embedder,
    )

    result = service.backfill(repo)

    assert embedder.commit_calls == ["sha2"]
    assert embedder.evidence_calls == ["https://github.com/owner/repo/discussions/1"]
    assert result.embedded == 2
    assert result.already_present == 1
    assert result.failed == 0
    persisted_ids = {chunk.source_id for chunk in store.get_all_embeddings(repo)}
    assert persisted_ids == {"sha1", "sha2", "https://github.com/owner/repo/discussions/1"}


def test_second_backfill_run_is_idempotent_and_embeds_nothing() -> None:
    repo = "repo-1"
    analyses = [_make_analysis(commit_sha="sha1"), _make_analysis(commit_sha="sha2")]
    evidence = [_make_evidence(discussion_url="https://github.com/owner/repo/discussions/1")]
    store = _FakeEmbeddingStore()
    embedder = _FakeEmbedder()
    service = EmbeddingBackfillService(
        commit_analysis_reader=_StubCommitAnalysisReader({repo: analyses}),
        discussion_evidence_reader=_StubDiscussionEvidenceReader({repo: evidence}),
        embedding_reader=store,
        embedding_writer=store,
        embedder=embedder,
    )

    first_result = service.backfill(repo)
    assert first_result.embedded == 3
    calls_after_first_run = len(embedder.commit_calls) + len(embedder.evidence_calls)

    second_result = service.backfill(repo)

    assert second_result.embedded == 0
    assert second_result.already_present == 3
    assert second_result.failed == 0
    assert len(embedder.commit_calls) + len(embedder.evidence_calls) == calls_after_first_run
    assert len(store.get_all_embeddings(repo)) == 3


def test_one_failing_item_does_not_prevent_others_from_being_embedded(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repo = "repo-1"
    analyses = [
        _make_analysis(commit_sha="sha1", summary="a very secret first summary"),
        _make_analysis(commit_sha="sha2", summary="a very secret second summary"),
        _make_analysis(commit_sha="sha3", summary="a very secret third summary"),
    ]
    embedder = _FakeEmbedder(commit_failures={"sha2"})
    store = _FakeEmbeddingStore()
    service = EmbeddingBackfillService(
        commit_analysis_reader=_StubCommitAnalysisReader({repo: analyses}),
        discussion_evidence_reader=_StubDiscussionEvidenceReader({repo: []}),
        embedding_reader=store,
        embedding_writer=store,
        embedder=embedder,
    )

    with caplog.at_level("WARNING"):
        result = service.backfill(repo)

    assert result.embedded == 2
    assert result.failed == 1
    persisted_ids = {chunk.source_id for chunk in store.get_all_embeddings(repo)}
    assert persisted_ids == {"sha1", "sha3"}
    assert "RuntimeError" in caplog.text
    assert "a very secret second summary" not in caplog.text
    assert "boom" not in caplog.text


def test_backfill_with_no_embedder_is_a_clean_no_op() -> None:
    repo = "repo-1"
    store = _FakeEmbeddingStore()
    service = EmbeddingBackfillService(
        commit_analysis_reader=_StubCommitAnalysisReader({repo: [_make_analysis()]}),
        discussion_evidence_reader=_StubDiscussionEvidenceReader({repo: [_make_evidence()]}),
        embedding_reader=store,
        embedding_writer=store,
        embedder=None,
    )

    result = service.backfill(repo)

    assert result.embedded == 0
    assert result.failed == 0
    assert result.already_present == 0
    assert store.get_all_embeddings(repo) == []
    assert service.estimate_backfill_calls(repo) == 0


def test_is_available_reflects_embedder_presence() -> None:
    """is_available distinguishes 'no OPENAI_API_KEY' (embedder None) from 'nothing missing'.

    Regression: without this, a no-key run is indistinguishable from an all-embedded run,
    because estimate_backfill_calls returns 0 in both cases.
    """
    store = _FakeEmbeddingStore()
    with_embedder = EmbeddingBackfillService(
        commit_analysis_reader=_StubCommitAnalysisReader({}),
        discussion_evidence_reader=_StubDiscussionEvidenceReader({}),
        embedding_reader=store,
        embedding_writer=store,
        embedder=_FakeEmbedder(),
    )
    without_embedder = EmbeddingBackfillService(
        commit_analysis_reader=_StubCommitAnalysisReader({}),
        discussion_evidence_reader=_StubDiscussionEvidenceReader({}),
        embedding_reader=store,
        embedding_writer=store,
        embedder=None,
    )

    assert with_embedder.is_available is True
    assert without_embedder.is_available is False


def test_missing_item_in_one_repository_does_not_affect_another() -> None:
    repo_a = "repo-a"
    repo_b = "repo-b"
    analyses = {
        repo_a: [_make_analysis(commit_sha="a-sha1")],
        repo_b: [_make_analysis(commit_sha="b-sha1")],
    }
    store = _FakeEmbeddingStore(
        initial=[
            _make_chunk(repository_id=repo_b, source_type="commit_analysis", source_id="b-sha1"),
        ]
    )
    embedder = _FakeEmbedder()
    service = EmbeddingBackfillService(
        commit_analysis_reader=_StubCommitAnalysisReader(analyses),
        discussion_evidence_reader=_StubDiscussionEvidenceReader({}),
        embedding_reader=store,
        embedding_writer=store,
        embedder=embedder,
    )

    assert service.estimate_backfill_calls(repo_a) == 1
    assert service.estimate_backfill_calls(repo_b) == 0

    result_a = service.backfill(repo_a)

    assert result_a.embedded == 1
    assert embedder.commit_calls == ["a-sha1"]
    assert {chunk.source_id for chunk in store.get_all_embeddings(repo_b)} == {"b-sha1"}
