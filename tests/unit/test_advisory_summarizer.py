import json
import logging

import pytest

from git_it.repository_ingestion.application.advisory_summarizer import AdvisorySummarizer
from git_it.repository_ingestion.application.ports import LLMMessage
from git_it.repository_ingestion.domain.advisories import SecurityAdvisory


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


def _make_advisory(
    *,
    ghsa_id: str = "GHSA-pmv8-rq9r-6j72",
    cve_id: str | None = "CVE-2026-12345",
    summary: str = "A vulnerability in dependency parsing.",
    description: str = "Detailed description of the vulnerability and its impact.",
    severity: str = "high",
    html_url: str = "https://github.com/owner/repo/security/advisories/GHSA-pmv8-rq9r-6j72",
    published_at: str | None = "2026-01-01T00:00:00Z",
) -> SecurityAdvisory:
    return SecurityAdvisory(
        ghsa_id=ghsa_id,
        cve_id=cve_id,
        summary=summary,
        description=description,
        severity=severity,
        html_url=html_url,
        published_at=published_at,
    )


def _valid_payload(
    *,
    summary: str = "This advisory describes a high-severity vulnerability, now patched.",
    confidence: float = 0.8,
    limitations: list[str] | None = None,
) -> dict:
    return {
        "summary": summary,
        "confidence": confidence,
        "limitations": limitations if limitations is not None else [],
    }


def _valid_json(**kwargs: object) -> str:
    return json.dumps(_valid_payload(**kwargs))  # type: ignore[arg-type]


def test_valid_response_produces_evidence_with_trusted_fields() -> None:
    advisory = _make_advisory()
    client = _StubLLMClient([_valid_json()])
    summarizer = AdvisorySummarizer(client, model="fake-model")

    result = summarizer.summarize([advisory])

    assert len(result) == 1
    evidence = result[0]
    assert evidence.summary == "This advisory describes a high-severity vulnerability, now patched."
    assert evidence.confidence == 0.8
    assert evidence.limitations == []
    assert evidence.ghsa_id == advisory.ghsa_id
    assert evidence.advisory_url == advisory.html_url
    assert evidence.severity == advisory.severity
    assert evidence.source_inputs == [advisory.ghsa_id]
    assert evidence.model == "fake-model"


def test_llm_supplied_url_is_ignored_trusted_advisory_url_wins() -> None:
    """The URL trust boundary: LLM output must never control the citation link."""
    advisory = _make_advisory()
    payload = _valid_payload()
    payload["advisory_url"] = "https://evil.com/x"
    client = _StubLLMClient([json.dumps(payload)])
    summarizer = AdvisorySummarizer(client, model="fake-model")

    result = summarizer.summarize([advisory])

    assert len(result) == 1
    assert result[0].advisory_url == advisory.html_url
    assert result[0].advisory_url != "https://evil.com/x"


def test_llm_supplied_severity_is_ignored_trusted_api_severity_wins() -> None:
    """severity is a trusted factual field from GitHub, never an LLM judgment."""
    advisory = _make_advisory(severity="critical")
    payload = _valid_payload()
    payload["severity"] = "low"
    client = _StubLLMClient([json.dumps(payload)])
    summarizer = AdvisorySummarizer(client, model="fake-model")

    result = summarizer.summarize([advisory])

    assert len(result) == 1
    assert result[0].severity == "critical"
    assert result[0].severity != "low"


def test_missing_summary_drops_advisory() -> None:
    advisory = _make_advisory()
    payload = _valid_payload()
    del payload["summary"]
    client = _StubLLMClient([json.dumps(payload)])
    summarizer = AdvisorySummarizer(client, model="fake-model")

    result = summarizer.summarize([advisory])

    assert result == []


def test_missing_confidence_drops_advisory() -> None:
    advisory = _make_advisory()
    payload = _valid_payload()
    del payload["confidence"]
    client = _StubLLMClient([json.dumps(payload)])
    summarizer = AdvisorySummarizer(client, model="fake-model")

    result = summarizer.summarize([advisory])

    assert result == []


def test_confidence_out_of_range_drops_advisory() -> None:
    advisory = _make_advisory()
    client = _StubLLMClient([_valid_json(confidence=2.0)])
    summarizer = AdvisorySummarizer(client, model="fake-model")

    result = summarizer.summarize([advisory])

    assert result == []


def test_invalid_non_json_response_drops_advisory() -> None:
    advisory = _make_advisory()
    client = _StubLLMClient(["this is not json at all"])
    summarizer = AdvisorySummarizer(client, model="fake-model")

    result = summarizer.summarize([advisory])

    assert result == []


def test_response_wrapped_in_markdown_code_fence_is_parsed() -> None:
    advisory = _make_advisory()
    wrapped = f"```json\n{_valid_json()}\n```"
    client = _StubLLMClient([wrapped])
    summarizer = AdvisorySummarizer(client, model="fake-model")

    result = summarizer.summarize([advisory])

    assert len(result) == 1
    expected_summary = "This advisory describes a high-severity vulnerability, now patched."
    assert result[0].summary == expected_summary


def test_one_llm_failure_does_not_abort_batch() -> None:
    a1 = _make_advisory(
        ghsa_id="GHSA-aaaa-bbbb-cccc",
        html_url="https://github.com/owner/repo/security/advisories/GHSA-aaaa-bbbb-cccc",
    )
    a2 = _make_advisory(
        ghsa_id="GHSA-dddd-eeee-ffff",
        html_url="https://github.com/owner/repo/security/advisories/GHSA-dddd-eeee-ffff",
    )
    a3 = _make_advisory(
        ghsa_id="GHSA-gggg-hhhh-iiii",
        html_url="https://github.com/owner/repo/security/advisories/GHSA-gggg-hhhh-iiii",
    )
    client = _StubLLMClient(
        [
            _valid_json(summary="first"),
            RuntimeError("boom"),
            _valid_json(summary="third"),
        ]
    )
    summarizer = AdvisorySummarizer(client, model="fake-model")

    result = summarizer.summarize([a1, a2, a3])

    assert len(result) == 2
    assert [e.ghsa_id for e in result] == ["GHSA-aaaa-bbbb-cccc", "GHSA-gggg-hhhh-iiii"]


def test_exactly_one_complete_call_per_advisory() -> None:
    a1 = _make_advisory(
        ghsa_id="GHSA-aaaa-bbbb-cccc",
        html_url="https://github.com/owner/repo/security/advisories/GHSA-aaaa-bbbb-cccc",
    )
    a2 = _make_advisory(
        ghsa_id="GHSA-dddd-eeee-ffff",
        html_url="https://github.com/owner/repo/security/advisories/GHSA-dddd-eeee-ffff",
    )
    client = _StubLLMClient([_valid_json(), _valid_json()])
    summarizer = AdvisorySummarizer(client, model="fake-model")

    summarizer.summarize([a1, a2])

    assert len(client.calls) == 2


def test_system_prompt_contains_untrusted_data_security_preamble() -> None:
    advisory = _make_advisory()
    client = _StubLLMClient([_valid_json()])
    summarizer = AdvisorySummarizer(client, model="fake-model")

    summarizer.summarize([advisory])

    system_messages = [m for m in client.calls[0] if m.role == "system"]
    assert system_messages
    assert "disregard it" in system_messages[0].content


def test_empty_advisory_list_returns_empty_and_makes_no_calls() -> None:
    client = _StubLLMClient([])
    summarizer = AdvisorySummarizer(client, model="fake-model")

    result = summarizer.summarize([])

    assert result == []
    assert client.calls == []


def test_advisory_url_validation_failure_drops_advisory_without_raising() -> None:
    """A malformed html_url on the trusted SecurityAdvisory fails AdvisoryEvidence's
    own validator; this must be caught and drop the item, not propagate."""
    advisory = _make_advisory(html_url="https://not-a-valid-advisory-url.example.com")
    client = _StubLLMClient([_valid_json()])
    summarizer = AdvisorySummarizer(client, model="fake-model")

    result = summarizer.summarize([advisory])

    assert result == []


def test_no_raw_description_or_response_leakage_on_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "SUPER_SECRET_ADVISORY_DESCRIPTION_SENTINEL_67890"
    advisory = _make_advisory(description=f"Vulnerability details containing {sentinel}.")
    client = _StubLLMClient([ValueError(f"malformed response containing {sentinel}")])
    summarizer = AdvisorySummarizer(client, model="fake-model")

    with caplog.at_level(logging.WARNING):
        result = summarizer.summarize([advisory])

    assert result == []
    assert "ValueError" in caplog.text
    assert sentinel not in caplog.text
