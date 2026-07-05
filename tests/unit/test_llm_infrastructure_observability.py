"""Batch 117 — proves the four infrastructure.llm call sites are wired into
spec 024's observe_llm_call with the correct, locked call_site strings:
"commit_analysis", "pattern_synthesis", "narrative_generation", and
"discussion_summarization". No real network/API calls — litellm/instructor are
monkeypatched, mirroring test_litellm_chat_client.py's approach.
"""

import logging
from typing import Any

import pytest

from git_it.repository_ingestion.application.ports import LLMMessage
from git_it.repository_ingestion.domain.analysis import CommitAnalysis, CommitCategory
from git_it.repository_ingestion.domain.patterns import PatternReport
from git_it.repository_ingestion.infrastructure.llm import (
    InstructorCommitAnalysisAdapter,
    InstructorPatternSynthesisAdapter,
    LiteLLMLLMClient,
    PatternSynthesisOutput,
)


def _observability_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "git_it.observability"]


class _FakeInstructorCompletions:
    def __init__(self, result: Any) -> None:
        self._result = result
        self.captured_kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> Any:
        self.captured_kwargs = kwargs
        return self._result


class _FakeInstructorChat:
    def __init__(self, completions: _FakeInstructorCompletions) -> None:
        self.completions = completions


class _FakeInstructorClient:
    def __init__(self, result: Any) -> None:
        self.completions = _FakeInstructorCompletions(result)
        self.chat = _FakeInstructorChat(self.completions)


def _install_fake_instructor(monkeypatch: pytest.MonkeyPatch, result: Any) -> _FakeInstructorClient:
    import instructor

    fake_client = _FakeInstructorClient(result)
    monkeypatch.setattr(instructor, "from_litellm", lambda _fn: fake_client)
    return fake_client


def test_analyze_commit_observed_with_commit_analysis_call_site(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="git_it.observability")
    analysis = CommitAnalysis(
        commit_sha="abc1234",
        summary="Added a feature",
        category=CommitCategory.FEATURE,
        confidence=0.9,
    )
    _install_fake_instructor(monkeypatch, analysis)

    adapter = InstructorCommitAnalysisAdapter(model="fake-model")
    result = adapter.analyze_commit(
        "system prompt", [LLMMessage(role="user", content="sha:abc1234\ndiff here")]
    )

    assert result is analysis
    records = _observability_records(caplog)
    assert len(records) == 1
    assert records[0].call_site == "commit_analysis"  # type: ignore[attr-defined]
    assert records[0].model == "fake-model"  # type: ignore[attr-defined]
    assert records[0].success is True  # type: ignore[attr-defined]


def test_pattern_synthesis_observed_with_pattern_synthesis_call_site(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="git_it.observability")
    _install_fake_instructor(monkeypatch, PatternSynthesisOutput(explanations=[]))

    adapter = InstructorPatternSynthesisAdapter(model="fake-model")
    report = PatternReport(repository_id="owner/repo", hotspots=[])

    result = adapter.synthesize(report)

    assert result == []
    records = _observability_records(caplog)
    assert len(records) == 1
    assert records[0].call_site == "pattern_synthesis"  # type: ignore[attr-defined]
    assert records[0].model == "fake-model"  # type: ignore[attr-defined]


def _install_fake_litellm_completion(monkeypatch: pytest.MonkeyPatch, content: str) -> None:
    from types import SimpleNamespace

    import litellm

    def _fake_completion(**kwargs: Any) -> SimpleNamespace:
        message = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    monkeypatch.setattr(litellm, "completion", _fake_completion)


def test_complete_defaults_to_narrative_generation_call_site(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="git_it.observability")
    _install_fake_litellm_completion(monkeypatch, "narrative text")

    client = LiteLLMLLMClient(model="fake-model")
    result = client.complete([LLMMessage(role="user", content="hi")])

    assert result == "narrative text"
    records = _observability_records(caplog)
    assert len(records) == 1
    assert records[0].call_site == "narrative_generation"  # type: ignore[attr-defined]


def test_complete_uses_discussion_summarization_call_site_when_constructed_for_it(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="git_it.observability")
    _install_fake_litellm_completion(monkeypatch, "summary text")

    client = LiteLLMLLMClient(model="fake-model", call_site="discussion_summarization")
    result = client.complete([LLMMessage(role="user", content="hi")])

    assert result == "summary text"
    records = _observability_records(caplog)
    assert len(records) == 1
    assert records[0].call_site == "discussion_summarization"  # type: ignore[attr-defined]
