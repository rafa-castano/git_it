"""Shared fixtures for unit tests.

Safety net against module-level state leakage
-----------------------------------------------
``git_it.api.routes.repos`` keeps two module-level dicts —
``_analyze_progress`` and ``_regen_progress`` — as an in-memory progress
store keyed by repository id. Some tests intentionally seed these dicts to
exercise progress-reporting/blocking behavior (e.g. the "delete blocked
while analysis is running" tests), and a few others POST to the analyze/
regenerate endpoints, which spawn a real background thread that writes into
these dicts.

Without a reset, an entry can leak from one test into another that reuses
the same default repository id (``"repo-abc"``), causing order-dependent
flakiness — a test can see stale ``running=True`` state it never set. This
autouse fixture clears both dicts before and after every test in this
directory, regardless of how a given test seeds or leaves them.
"""

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _reset_progress_dicts() -> Iterator[None]:
    from git_it.api.routes.repos import _analyze_progress, _regen_progress

    _analyze_progress.clear()
    _regen_progress.clear()
    yield
    _analyze_progress.clear()
    _regen_progress.clear()
