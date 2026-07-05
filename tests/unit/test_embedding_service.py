from datetime import UTC, datetime

import pytest

from git_it.repository_ingestion.application.embedding_service import EmbeddingService
from git_it.repository_ingestion.domain.analysis import CommitAnalysis, CommitCategory
from git_it.repository_ingestion.domain.discussions import DiscussionEvidence


class _StubEmbeddingClient:
    """Fake EmbeddingClient returning scripted responses, one per call, in order."""

    def __init__(
        self, responses: list[list[float] | Exception], *, model: str = "fake-embed-model"
    ) -> None:
        self._responses = list(responses)
        self._model = model
        self.calls: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _make_analysis(
    *,
    commit_sha: str = "abc123",
    summary: str = "Fixed a SQL injection vulnerability in the login form.",
) -> CommitAnalysis:
    return CommitAnalysis(
        commit_sha=commit_sha,
        summary=summary,
        summary_beginner="Beginner variant text that must never be embedded.",
        summary_expert="Expert variant text that must never be embedded.",
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


def test_embed_commit_analysis_returns_chunk_with_summary_text_only() -> None:
    analysis = _make_analysis()
    client = _StubEmbeddingClient([[0.1, 0.2, 0.3]])
    service = EmbeddingService(client)

    chunk = service.embed_commit_analysis("repo-1", analysis)

    assert chunk is not None
    assert chunk.repository_id == "repo-1"
    assert chunk.source_type == "commit_analysis"
    assert chunk.source_id == analysis.commit_sha
    assert chunk.text == analysis.summary
    assert chunk.vector == [0.1, 0.2, 0.3]


def test_embed_commit_analysis_never_embeds_beginner_or_expert_variant() -> None:
    analysis = _make_analysis()
    client = _StubEmbeddingClient([[0.1, 0.2, 0.3]])
    service = EmbeddingService(client)

    service.embed_commit_analysis("repo-1", analysis)

    assert client.calls == [analysis.summary]
    assert client.calls[0] != analysis.summary_beginner
    assert client.calls[0] != analysis.summary_expert


def test_embed_discussion_evidence_returns_chunk_with_full_discussion_url_as_source_id() -> None:
    evidence = _make_evidence()
    client = _StubEmbeddingClient([[0.4, 0.5, 0.6]])
    service = EmbeddingService(client)

    chunk = service.embed_discussion_evidence("repo-1", evidence)

    assert chunk is not None
    assert chunk.repository_id == "repo-1"
    assert chunk.source_type == "discussion_evidence"
    # Locked decision: source_id holds the full, citation-ready discussion_url,
    # not the bare discussion_id.
    assert chunk.source_id == evidence.discussion_url
    assert chunk.source_id != evidence.discussion_id
    assert chunk.text == evidence.summary
    assert chunk.vector == [0.4, 0.5, 0.6]


def test_embed_discussion_evidence_only_passes_summary_text_to_embed() -> None:
    evidence = _make_evidence()
    client = _StubEmbeddingClient([[0.4, 0.5, 0.6]])
    service = EmbeddingService(client)

    service.embed_discussion_evidence("repo-1", evidence)

    assert client.calls == [evidence.summary]


def test_embed_commit_analysis_returns_none_and_logs_only_exception_type_on_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    analysis = _make_analysis(summary="a very secret summary text that must never be logged")
    client = _StubEmbeddingClient([RuntimeError("boom: sensitive detail")])
    service = EmbeddingService(client)

    with caplog.at_level("WARNING"):
        result = service.embed_commit_analysis("repo-1", analysis)

    assert result is None
    assert "RuntimeError" in caplog.text
    assert "boom" not in caplog.text
    assert "sensitive detail" not in caplog.text
    assert analysis.summary not in caplog.text


def test_embed_discussion_evidence_returns_none_and_logs_only_exception_type_on_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    evidence = _make_evidence(summary="another secret summary that must never be logged")
    client = _StubEmbeddingClient([ValueError("malformed response: secret payload")])
    service = EmbeddingService(client)

    with caplog.at_level("WARNING"):
        result = service.embed_discussion_evidence("repo-1", evidence)

    assert result is None
    assert "ValueError" in caplog.text
    assert "malformed response" not in caplog.text
    assert "secret payload" not in caplog.text
    assert evidence.summary not in caplog.text


def test_one_failing_commit_analysis_does_not_prevent_others_from_embedding() -> None:
    a1 = _make_analysis(commit_sha="sha1", summary="first summary")
    a2 = _make_analysis(commit_sha="sha2", summary="second summary")
    a3 = _make_analysis(commit_sha="sha3", summary="third summary")
    client = _StubEmbeddingClient(
        [
            [0.1, 0.1],
            RuntimeError("boom"),
            [0.3, 0.3],
        ]
    )
    service = EmbeddingService(client)

    results = [service.embed_commit_analysis("repo-1", a) for a in (a1, a2, a3)]

    assert results[0] is not None
    assert results[0].source_id == "sha1"
    assert results[1] is None
    assert results[2] is not None
    assert results[2].source_id == "sha3"
