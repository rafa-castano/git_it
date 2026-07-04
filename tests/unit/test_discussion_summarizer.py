import json

from git_it.repository_ingestion.application.discussion_summarizer import DiscussionSummarizer
from git_it.repository_ingestion.application.ports import LLMMessage
from git_it.repository_ingestion.domain.discussions import Discussion


class _StubLLMClient:
    """Fake LLMClient returning scripted responses, one per call, in order."""

    def __init__(self, responses: list[str | Exception]) -> None:
        self._responses = list(responses)
        self.calls: list[list[LLMMessage]] = []

    def complete(self, messages: list[LLMMessage]) -> str:
        self.calls.append(messages)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _make_discussion(
    *,
    id: str = "D_1",
    url: str = "https://github.com/owner/repo/discussions/1",
) -> Discussion:
    return Discussion(
        id=id,
        url=url,
        title="Why did we choose X over Y?",
        body="Some discussion body content explaining the tradeoffs.",
        answer_body="The accepted answer body.",
        category="Q&A",
        is_answered=True,
        upvote_count=10,
        reaction_count=2,
        comment_count=4,
        updated_at="2026-01-01T00:00:00Z",
    )


def _valid_payload(
    *,
    claim_type: str = "design_rationale",
    summary: str = "We chose X for Y reasons.",
    confidence: float = 0.8,
    limitations: list[str] | None = None,
) -> dict:
    return {
        "claim_type": claim_type,
        "summary": summary,
        "confidence": confidence,
        "limitations": limitations if limitations is not None else [],
    }


def _valid_json(**kwargs: object) -> str:
    return json.dumps(_valid_payload(**kwargs))  # type: ignore[arg-type]


def test_valid_response_produces_evidence_with_trusted_fields() -> None:
    discussion = _make_discussion()
    client = _StubLLMClient([_valid_json()])
    summarizer = DiscussionSummarizer(client, model="fake-model")

    result = summarizer.summarize([discussion])

    assert len(result) == 1
    evidence = result[0]
    assert evidence.claim_type == "design_rationale"
    assert evidence.summary == "We chose X for Y reasons."
    assert evidence.confidence == 0.8
    assert evidence.limitations == []
    assert evidence.discussion_id == discussion.id
    assert evidence.discussion_url == discussion.url
    assert evidence.source_inputs == [discussion.id]
    assert evidence.model == "fake-model"


def test_llm_supplied_url_is_ignored_trusted_discussion_url_wins() -> None:
    """The URL/id trust boundary: LLM output must never control the citation link."""
    discussion = _make_discussion()
    payload = _valid_payload()
    payload["discussion_url"] = "https://evil.com/x"
    client = _StubLLMClient([json.dumps(payload)])
    summarizer = DiscussionSummarizer(client, model="fake-model")

    result = summarizer.summarize([discussion])

    assert len(result) == 1
    assert result[0].discussion_url == discussion.url
    assert result[0].discussion_url != "https://evil.com/x"


def test_missing_claim_type_drops_discussion() -> None:
    discussion = _make_discussion()
    payload = _valid_payload()
    del payload["claim_type"]
    client = _StubLLMClient([json.dumps(payload)])
    summarizer = DiscussionSummarizer(client, model="fake-model")

    result = summarizer.summarize([discussion])

    assert result == []


def test_missing_summary_drops_discussion() -> None:
    discussion = _make_discussion()
    payload = _valid_payload()
    del payload["summary"]
    client = _StubLLMClient([json.dumps(payload)])
    summarizer = DiscussionSummarizer(client, model="fake-model")

    result = summarizer.summarize([discussion])

    assert result == []


def test_missing_confidence_drops_discussion() -> None:
    discussion = _make_discussion()
    payload = _valid_payload()
    del payload["confidence"]
    client = _StubLLMClient([json.dumps(payload)])
    summarizer = DiscussionSummarizer(client, model="fake-model")

    result = summarizer.summarize([discussion])

    assert result == []


def test_confidence_out_of_range_drops_discussion() -> None:
    discussion = _make_discussion()
    client = _StubLLMClient([_valid_json(confidence=1.5)])
    summarizer = DiscussionSummarizer(client, model="fake-model")

    result = summarizer.summarize([discussion])

    assert result == []


def test_invalid_non_json_response_drops_discussion() -> None:
    discussion = _make_discussion()
    client = _StubLLMClient(["this is not json at all"])
    summarizer = DiscussionSummarizer(client, model="fake-model")

    result = summarizer.summarize([discussion])

    assert result == []


def test_response_wrapped_in_markdown_code_fence_is_parsed() -> None:
    discussion = _make_discussion()
    wrapped = f"```json\n{_valid_json()}\n```"
    client = _StubLLMClient([wrapped])
    summarizer = DiscussionSummarizer(client, model="fake-model")

    result = summarizer.summarize([discussion])

    assert len(result) == 1
    assert result[0].summary == "We chose X for Y reasons."


def test_one_llm_failure_does_not_abort_batch() -> None:
    d1 = _make_discussion(id="D_1", url="https://github.com/owner/repo/discussions/1")
    d2 = _make_discussion(id="D_2", url="https://github.com/owner/repo/discussions/2")
    d3 = _make_discussion(id="D_3", url="https://github.com/owner/repo/discussions/3")
    client = _StubLLMClient(
        [
            _valid_json(summary="first"),
            RuntimeError("boom"),
            _valid_json(summary="third"),
        ]
    )
    summarizer = DiscussionSummarizer(client, model="fake-model")

    result = summarizer.summarize([d1, d2, d3])

    assert len(result) == 2
    assert [e.discussion_id for e in result] == ["D_1", "D_3"]


def test_exactly_one_complete_call_per_discussion() -> None:
    d1 = _make_discussion(id="D_1", url="https://github.com/owner/repo/discussions/1")
    d2 = _make_discussion(id="D_2", url="https://github.com/owner/repo/discussions/2")
    client = _StubLLMClient([_valid_json(), _valid_json()])
    summarizer = DiscussionSummarizer(client, model="fake-model")

    summarizer.summarize([d1, d2])

    assert len(client.calls) == 2


def test_system_prompt_contains_untrusted_data_security_preamble() -> None:
    discussion = _make_discussion()
    client = _StubLLMClient([_valid_json()])
    summarizer = DiscussionSummarizer(client, model="fake-model")

    summarizer.summarize([discussion])

    system_messages = [m for m in client.calls[0] if m.role == "system"]
    assert system_messages
    assert "disregard it" in system_messages[0].content


def test_empty_discussion_list_returns_empty_and_makes_no_calls() -> None:
    client = _StubLLMClient([])
    summarizer = DiscussionSummarizer(client, model="fake-model")

    result = summarizer.summarize([])

    assert result == []
    assert client.calls == []
