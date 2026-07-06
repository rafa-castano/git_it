import json
import logging

import pytest

from git_it.repository_ingestion.application.ports import LLMMessage
from git_it.repository_ingestion.application.release_summarizer import ReleaseSummarizer
from git_it.repository_ingestion.domain.releases import Release


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


def _make_release(
    *,
    tag_name: str = "v1.0.0",
    name: str | None = "Version 1.0.0",
    body: str | None = "Adds feature X and fixes bug Y.",
    html_url: str = "https://github.com/owner/repo/releases/tag/v1.0.0",
    published_at: str | None = "2026-01-01T00:00:00Z",
    prerelease: bool = False,
) -> Release:
    return Release(
        tag_name=tag_name,
        name=name,
        body=body,
        html_url=html_url,
        published_at=published_at,
        prerelease=prerelease,
    )


def _valid_payload(
    *,
    claim_type: str = "feature_release",
    summary: str = "This release adds feature X.",
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
    release = _make_release()
    client = _StubLLMClient([_valid_json()])
    summarizer = ReleaseSummarizer(client, model="fake-model")

    result = summarizer.summarize([release])

    assert len(result) == 1
    evidence = result[0]
    assert evidence.claim_type == "feature_release"
    assert evidence.summary == "This release adds feature X."
    assert evidence.confidence == 0.8
    assert evidence.limitations == []
    assert evidence.tag_name == release.tag_name
    assert evidence.release_url == release.html_url
    assert evidence.source_inputs == [release.tag_name]
    assert evidence.model == "fake-model"


def test_llm_supplied_url_is_ignored_trusted_release_url_wins() -> None:
    """The URL trust boundary: LLM output must never control the citation link."""
    release = _make_release()
    payload = _valid_payload()
    payload["release_url"] = "https://evil.com/x"
    client = _StubLLMClient([json.dumps(payload)])
    summarizer = ReleaseSummarizer(client, model="fake-model")

    result = summarizer.summarize([release])

    assert len(result) == 1
    assert result[0].release_url == release.html_url
    assert result[0].release_url != "https://evil.com/x"


def test_missing_claim_type_drops_release() -> None:
    release = _make_release()
    payload = _valid_payload()
    del payload["claim_type"]
    client = _StubLLMClient([json.dumps(payload)])
    summarizer = ReleaseSummarizer(client, model="fake-model")

    result = summarizer.summarize([release])

    assert result == []


def test_missing_summary_drops_release() -> None:
    release = _make_release()
    payload = _valid_payload()
    del payload["summary"]
    client = _StubLLMClient([json.dumps(payload)])
    summarizer = ReleaseSummarizer(client, model="fake-model")

    result = summarizer.summarize([release])

    assert result == []


def test_missing_confidence_drops_release() -> None:
    release = _make_release()
    payload = _valid_payload()
    del payload["confidence"]
    client = _StubLLMClient([json.dumps(payload)])
    summarizer = ReleaseSummarizer(client, model="fake-model")

    result = summarizer.summarize([release])

    assert result == []


def test_confidence_out_of_range_drops_release() -> None:
    release = _make_release()
    client = _StubLLMClient([_valid_json(confidence=1.5)])
    summarizer = ReleaseSummarizer(client, model="fake-model")

    result = summarizer.summarize([release])

    assert result == []


def test_invalid_claim_type_drops_release() -> None:
    release = _make_release()
    client = _StubLLMClient([_valid_json(claim_type="not_a_real_type")])
    summarizer = ReleaseSummarizer(client, model="fake-model")

    result = summarizer.summarize([release])

    assert result == []


def test_invalid_non_json_response_drops_release() -> None:
    release = _make_release()
    client = _StubLLMClient(["this is not json at all"])
    summarizer = ReleaseSummarizer(client, model="fake-model")

    result = summarizer.summarize([release])

    assert result == []


def test_response_wrapped_in_markdown_code_fence_is_parsed() -> None:
    release = _make_release()
    wrapped = f"```json\n{_valid_json()}\n```"
    client = _StubLLMClient([wrapped])
    summarizer = ReleaseSummarizer(client, model="fake-model")

    result = summarizer.summarize([release])

    assert len(result) == 1
    assert result[0].summary == "This release adds feature X."


def test_one_llm_failure_does_not_abort_batch() -> None:
    r1 = _make_release(
        tag_name="v1.0.0", html_url="https://github.com/owner/repo/releases/tag/v1.0.0"
    )
    r2 = _make_release(
        tag_name="v1.1.0", html_url="https://github.com/owner/repo/releases/tag/v1.1.0"
    )
    r3 = _make_release(
        tag_name="v1.2.0", html_url="https://github.com/owner/repo/releases/tag/v1.2.0"
    )
    client = _StubLLMClient(
        [
            _valid_json(summary="first"),
            RuntimeError("boom"),
            _valid_json(summary="third"),
        ]
    )
    summarizer = ReleaseSummarizer(client, model="fake-model")

    result = summarizer.summarize([r1, r2, r3])

    assert len(result) == 2
    assert [e.tag_name for e in result] == ["v1.0.0", "v1.2.0"]


def test_exactly_one_complete_call_per_release() -> None:
    r1 = _make_release(
        tag_name="v1.0.0", html_url="https://github.com/owner/repo/releases/tag/v1.0.0"
    )
    r2 = _make_release(
        tag_name="v1.1.0", html_url="https://github.com/owner/repo/releases/tag/v1.1.0"
    )
    client = _StubLLMClient([_valid_json(), _valid_json()])
    summarizer = ReleaseSummarizer(client, model="fake-model")

    summarizer.summarize([r1, r2])

    assert len(client.calls) == 2


def test_system_prompt_contains_untrusted_data_security_preamble() -> None:
    release = _make_release()
    client = _StubLLMClient([_valid_json()])
    summarizer = ReleaseSummarizer(client, model="fake-model")

    summarizer.summarize([release])

    system_messages = [m for m in client.calls[0] if m.role == "system"]
    assert system_messages
    assert "disregard it" in system_messages[0].content


def test_empty_release_list_returns_empty_and_makes_no_calls() -> None:
    client = _StubLLMClient([])
    summarizer = ReleaseSummarizer(client, model="fake-model")

    result = summarizer.summarize([])

    assert result == []
    assert client.calls == []


def test_release_url_validation_failure_drops_release_without_raising() -> None:
    """A malformed html_url on the trusted Release fails ReleaseEvidence's own
    validator; this must be caught and drop the item, not propagate."""
    release = _make_release(html_url="https://not-a-valid-release-url.example.com")
    client = _StubLLMClient([_valid_json()])
    summarizer = ReleaseSummarizer(client, model="fake-model")

    result = summarizer.summarize([release])

    assert result == []


def test_no_raw_body_or_response_leakage_on_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "SUPER_SECRET_RELEASE_BODY_SENTINEL_12345"
    release = _make_release(body=f"Release notes containing {sentinel}.")
    client = _StubLLMClient([ValueError(f"malformed response containing {sentinel}")])
    summarizer = ReleaseSummarizer(client, model="fake-model")

    with caplog.at_level(logging.WARNING):
        result = summarizer.summarize([release])

    assert result == []
    assert "ValueError" in caplog.text
    assert sentinel not in caplog.text
