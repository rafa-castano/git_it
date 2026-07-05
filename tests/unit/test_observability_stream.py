"""Batch 117 — observe_llm_call_stream: generator-aware observability wrapper.

Spec 024's observe_llm_call decorator, applied naively to a generator function,
would only measure the time to *create* the generator (near-instant) rather
than the full time a caller spends consuming it, and would report success even
if the underlying stream raises mid-iteration. observe_llm_call_stream closes
that gap: timing starts when the generator is first iterated, and the
observation is only built/emitted once the stream is fully exhausted or raises
during iteration.
"""

import logging
import time
from collections.abc import Iterator

import pytest

from git_it.repository_ingestion.infrastructure.observability import (
    observe_llm_call_stream,
)


def _observability_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "git_it.observability"]


class _FakeStreamingClient:
    def __init__(self, model: str = "fake-model") -> None:
        self._model = model

    @observe_llm_call_stream("fake_stream_call_site")
    def stream(self, chunks: list[str]) -> Iterator[str]:
        yield from chunks


class _FailingStreamingClient:
    def __init__(self, model: str = "fake-model") -> None:
        self._model = model

    @observe_llm_call_stream("fake_stream_call_site")
    def stream(self, chunks: list[str]) -> Iterator[str]:
        yield from chunks
        raise ValueError("boom mid-stream")


class _SlowStreamingClient:
    def __init__(self, model: str = "fake-model") -> None:
        self._model = model

    @observe_llm_call_stream("fake_stream_call_site")
    def stream(self, chunks: list[str]) -> Iterator[str]:
        for chunk in chunks:
            time.sleep(0.05)
            yield chunk


def test_creating_the_generator_emits_no_observation_until_consumed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="git_it.observability")
    client = _FakeStreamingClient()

    generator = client.stream(["a", "b"])

    # Merely calling the decorated method must not have emitted anything yet —
    # observation only fires once the stream is exhausted.
    assert _observability_records(caplog) == []
    list(generator)
    assert len(_observability_records(caplog)) == 1


def test_successful_full_consumption_emits_one_record_with_success_true(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="git_it.observability")
    client = _FakeStreamingClient()

    result = list(client.stream(["a", "b", "c"]))

    assert result == ["a", "b", "c"]
    records = _observability_records(caplog)
    assert len(records) == 1
    record = records[0]
    assert record.success is True  # type: ignore[attr-defined]
    assert record.error_type is None  # type: ignore[attr-defined]
    assert record.call_site == "fake_stream_call_site"  # type: ignore[attr-defined]
    assert record.model == "fake-model"  # type: ignore[attr-defined]


def test_duration_reflects_full_stream_consumption_not_generator_creation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="git_it.observability")
    client = _SlowStreamingClient()

    # Three chunks, each preceded by a 50ms sleep inside the generator body —
    # if duration were measured at generator-creation time it would be ~0.
    list(client.stream(["a", "b", "c"]))

    record = _observability_records(caplog)[0]
    assert record.duration_ms >= 100  # type: ignore[attr-defined]


def test_exception_mid_stream_emits_failure_record_and_still_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="git_it.observability")
    client = _FailingStreamingClient()

    consumed: list[str] = []
    with pytest.raises(ValueError, match="boom mid-stream"):
        for chunk in client.stream(["a", "b"]):
            consumed.append(chunk)

    assert consumed == ["a", "b"]  # the caller did see the chunks before the raise
    records = _observability_records(caplog)
    assert len(records) == 1
    record = records[0]
    assert record.success is False  # type: ignore[attr-defined]
    assert record.error_type == "ValueError"  # type: ignore[attr-defined]


def test_partial_consumption_without_error_emits_no_record(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If the caller stops iterating early (no exception, no exhaustion), no
    observation is emitted — there is no well-defined "duration" for a stream
    the caller abandoned rather than finished or that raised."""
    caplog.set_level(logging.INFO, logger="git_it.observability")
    client = _FakeStreamingClient()

    generator = client.stream(["a", "b", "c"])
    next(generator)  # consume only the first item

    assert _observability_records(caplog) == []
