import logging
import time

import pytest

from git_it.repository_ingestion.infrastructure import observability as obs_module
from git_it.repository_ingestion.infrastructure.observability import (
    LLMCallObservation,
    observe_llm_call,
)

_SENTINEL = "sentinel-do-not-leak-xyz123"


class _FakeClientNoModel:
    """A client with no _model attribute — proves the 'unknown' fallback."""

    @observe_llm_call("fake_call_site")
    def call(self, text: str) -> str:
        return f"response for {text}"


class _FakeClient:
    def __init__(self, model: str = "fake-model") -> None:
        self._model = model

    @observe_llm_call("fake_call_site")
    def call(self, text: str) -> str:
        time.sleep(0.1)  # guarantee a measurable, non-zero duration_ms (coarse clock resolution)
        return f"response for {text}"


class _FakeClientWithRepo:
    def __init__(self, model: str = "fake-model", repository_id: str | None = None) -> None:
        self._model = model
        self._repository_id = repository_id

    @observe_llm_call("fake_call_site")
    def call(self, text: str) -> str:
        return f"response for {text}"


class _FailingClient:
    def __init__(self, model: str = "fake-model") -> None:
        self._model = model

    @observe_llm_call("fake_call_site")
    def call(self, text: str) -> str:
        raise ValueError("boom")


def _observability_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "git_it.observability"]


def test_successful_call_emits_one_log_record_and_returns_original_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="git_it.observability")
    client = _FakeClient(model="fake-model")

    result = client.call("hello")

    assert result == "response for hello"
    records = _observability_records(caplog)
    assert len(records) == 1
    record = records[0]
    assert record.success is True  # type: ignore[attr-defined]
    assert record.error_type is None  # type: ignore[attr-defined]
    assert record.duration_ms > 0  # type: ignore[attr-defined]
    assert record.call_site == "fake_call_site"  # type: ignore[attr-defined]
    assert record.model == "fake-model"  # type: ignore[attr-defined]


def test_failing_call_emits_log_record_and_reraises_original_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="git_it.observability")
    client = _FailingClient()

    with pytest.raises(ValueError, match="boom"):
        client.call("hello")

    records = _observability_records(caplog)
    assert len(records) == 1
    record = records[0]
    assert record.success is False  # type: ignore[attr-defined]
    assert record.error_type == "ValueError"  # type: ignore[attr-defined]


def test_call_without_model_attribute_logs_unknown_model(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="git_it.observability")
    client = _FakeClientNoModel()

    result = client.call("hello")

    assert result == "response for hello"
    records = _observability_records(caplog)
    assert len(records) == 1
    assert records[0].model == "unknown"  # type: ignore[attr-defined]


def test_tokens_and_cost_are_none_when_not_extractable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="git_it.observability")
    client = _FakeClient()

    client.call("hello")

    record = _observability_records(caplog)[0]
    assert record.tokens_in is None  # type: ignore[attr-defined]
    assert record.tokens_out is None  # type: ignore[attr-defined]
    assert record.tokens_total is None  # type: ignore[attr-defined]
    assert record.estimated_cost_usd is None  # type: ignore[attr-defined]


def test_repository_id_is_none_when_instance_has_no_repository_id_attribute(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="git_it.observability")
    client = _FakeClient()

    client.call("hello")

    record = _observability_records(caplog)[0]
    assert record.repository_id is None  # type: ignore[attr-defined]


def test_repository_id_is_populated_when_instance_has_repository_id_attribute(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="git_it.observability")
    client = _FakeClientWithRepo(repository_id="owner/repo")

    client.call("hello")

    record = _observability_records(caplog)[0]
    assert record.repository_id == "owner/repo"  # type: ignore[attr-defined]


def test_no_content_leakage_in_log_record_on_success(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="git_it.observability")
    client = _FakeClient()

    result = client.call(_SENTINEL)

    assert _SENTINEL in result  # sanity: the sentinel really is in the return value
    record = _observability_records(caplog)[0]
    assert _SENTINEL not in record.getMessage()
    assert _SENTINEL not in repr(record.__dict__)


def test_no_content_leakage_in_log_record_on_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="git_it.observability")

    class _FailingClientWithSentinel:
        _model = "fake-model"

        @observe_llm_call("fake_call_site")
        def call(self, text: str) -> str:
            raise ValueError(f"boom with {_SENTINEL}")

    client = _FailingClientWithSentinel()
    with pytest.raises(ValueError):
        client.call(_SENTINEL)

    record = _observability_records(caplog)[0]
    assert _SENTINEL not in record.getMessage()
    assert _SENTINEL not in repr(record.__dict__)


def test_broken_observation_step_does_not_break_successful_call(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)

    def _broken_emit(observation: LLMCallObservation) -> None:
        raise RuntimeError("emit exploded")

    monkeypatch.setattr(obs_module, "_emit_observation", _broken_emit)
    client = _FakeClient()

    result = client.call("hello")

    assert result == "response for hello"
    assert any(
        record.levelno == logging.WARNING and "observability" in record.message.lower()
        for record in caplog.records
    )


def test_broken_observation_step_does_not_swallow_original_exception(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)

    def _broken_emit(observation: LLMCallObservation) -> None:
        raise RuntimeError("emit exploded")

    monkeypatch.setattr(obs_module, "_emit_observation", _broken_emit)
    client = _FailingClient()

    with pytest.raises(ValueError, match="boom"):
        client.call("hello")

    assert any(
        record.levelno == logging.WARNING and "observability" in record.message.lower()
        for record in caplog.records
    )


def test_decorated_method_preserves_name_and_docstring() -> None:
    client = _FakeClient()
    assert client.call.__name__ == "call"
