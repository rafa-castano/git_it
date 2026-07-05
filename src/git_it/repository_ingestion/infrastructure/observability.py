"""Structured LLM call observability (spec 024).

Provides ``observe_llm_call``, a decorator any current or future LLM/embedding
client method can apply to emit exactly one structured, metadata-only log
record per call via the dedicated ``git_it.observability`` logger.

This module never logs prompt content, response content, or any other call
argument/return value directly -- only the fixed ``LLMCallObservation`` field
set (see spec 024, Security considerations). Logging itself is best-effort:
a failure while building or emitting the observation is caught and reported
as a warning, and never affects the wrapped call's own return value or
raised exception.
"""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ParamSpec, TypeVar

_logger = logging.getLogger(__name__)
_observability_logger = logging.getLogger("git_it.observability")

_UNKNOWN_MODEL = "unknown"

P = ParamSpec("P")
R = TypeVar("R")


@dataclass(frozen=True)
class LLMCallObservation:
    """The structured, metadata-only payload emitted per LLM/embedding call.

    Never persisted to a database -- only logged. Never carries prompt or
    response content: there is no "content"/"text" field to accidentally
    populate.
    """

    call_site: str
    model: str
    duration_ms: float
    success: bool
    error_type: str | None
    tokens_in: int | None
    tokens_out: int | None
    tokens_total: int | None
    estimated_cost_usd: float | None
    repository_id: str | None


def _extract_model(self_arg: Any) -> str:
    """Best-effort duck-typed model name lookup on the wrapped instance."""
    return getattr(self_arg, "_model", _UNKNOWN_MODEL)


def _extract_repository_id(self_arg: Any) -> str | None:
    """Best-effort duck-typed repository_id lookup on the wrapped instance."""
    repository_id = getattr(self_arg, "_repository_id", None)
    if repository_id is None:
        repository_id = getattr(self_arg, "repository_id", None)
    return repository_id


def _emit_observation(observation: LLMCallObservation) -> None:
    """Emit the structured log record for one observed call.

    Kept as a small, separately-callable function so tests can simulate a
    broken observation step (spec 024 acceptance criterion: a logging
    failure never breaks the underlying call).
    """
    _observability_logger.info(
        "llm call observed",
        extra={
            "call_site": observation.call_site,
            "model": observation.model,
            "duration_ms": observation.duration_ms,
            "success": observation.success,
            "error_type": observation.error_type,
            "tokens_in": observation.tokens_in,
            "tokens_out": observation.tokens_out,
            "tokens_total": observation.tokens_total,
            "estimated_cost_usd": observation.estimated_cost_usd,
            "repository_id": observation.repository_id,
        },
    )


def _build_and_emit(
    *,
    call_site: str,
    self_arg: Any,
    start: float,
    success: bool,
    error_type: str | None,
) -> None:
    """Build the observation and emit it, never letting a failure escape."""
    try:
        duration_ms = (time.monotonic() - start) * 1000
        observation = LLMCallObservation(
            call_site=call_site,
            model=_extract_model(self_arg),
            duration_ms=duration_ms,
            success=success,
            error_type=error_type,
            tokens_in=None,
            tokens_out=None,
            tokens_total=None,
            estimated_cost_usd=None,
            repository_id=_extract_repository_id(self_arg),
        )
        _emit_observation(observation)
    except Exception as log_exc:  # noqa: BLE001 - observability must never break the call
        _logger.warning("observability logging failed: %s", type(log_exc).__name__)


def observe_llm_call(call_site: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator factory wrapping an instance method with observability.

    The wrapped method's public signature, return type, and raised
    exceptions are unchanged -- this is a pure cross-cutting observer, never
    a participant in the call's own behavior.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            self_arg = args[0] if args else None
            start = time.monotonic()
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                _build_and_emit(
                    call_site=call_site,
                    self_arg=self_arg,
                    start=start,
                    success=False,
                    error_type=type(exc).__name__,
                )
                raise
            _build_and_emit(
                call_site=call_site,
                self_arg=self_arg,
                start=start,
                success=True,
                error_type=None,
            )
            return result

        return wrapper

    return decorator
