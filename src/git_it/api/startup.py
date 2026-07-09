"""Automatic silent background refresh at server startup (spec 033).

Once per server process, the served app runs the spec-028 batch refresh
(``RefreshAllService.refresh_all``) a single time, in a background daemon thread,
without blocking startup or any request. It is failure-isolated (errors are logged by
exception type name only — never a message that could carry a tokened ``git fetch`` URL),
single-flight (a process-level non-blocking lock), and opt-in (only the served
module-level app enables it, so the test suite never spawns a refresh thread).

Feasible now only because of spec 030: without incremental extraction a per-startup full
refresh would re-``git diff`` the entire history of every repository on every launch.
"""

import logging
import os
import threading
from pathlib import Path

from git_it.repository_ingestion.composition import (
    build_refresh_all_service,
    database_is_provisioned,
)

_logger = logging.getLogger(__name__)

# Process-level single-flight guard: at most one auto-refresh runs at a time (AC-05).
_refresh_lock = threading.Lock()


def resolve_startup_project_root(explicit: Path | None) -> Path:
    """Resolve the project root for the background refresh (spec 033 AC-08).

    Mirrors ``deps.get_project_root``: an explicit value (``app.state.project_root``)
    wins, else ``GIT_IT_DATA_DIR``, else the current working directory. Used at startup
    where there is no request to read state from.
    """
    if explicit is not None:
        return explicit
    data_dir = os.environ.get("GIT_IT_DATA_DIR")
    return Path(data_dir) if data_dir else Path.cwd()


def run_startup_refresh(project_root: Path) -> None:
    """Synchronous refresh body — run once from the background thread (spec 033).

    Skips entirely when the database is not provisioned (AC-06). Otherwise builds the
    spec-028 ``RefreshAllService`` and runs it, logging an aggregate (counts only) on
    success. Any exception is caught and logged by type name only (AC-04) so a failed
    refresh can never crash the server or leak a tokened URL.
    """
    try:
        if not database_is_provisioned(project_root=project_root):
            return
        service = build_refresh_all_service(project_root=project_root)
        result = service.refresh_all()
        _logger.info(
            "startup refresh complete: %d/%d repositories, %d new commits, %d failed",
            result.refreshed_count,
            result.total_repositories,
            result.total_new_commits,
            result.failed_count,
        )
    except Exception as exc:  # noqa: BLE001 - a failed refresh must never crash the server
        _logger.warning("startup refresh failed: %s", type(exc).__name__)


def start_background_refresh(project_root: Path) -> threading.Thread | None:
    """Spawn a daemon thread running ``run_startup_refresh`` once, or no-op if one is
    already running (single-flight). Returns the thread, or ``None`` when skipped.

    Non-blocking: the caller (the ASGI startup lifespan) returns immediately; the refresh
    runs off the request path (spec 033 AC-01/AC-02/AC-05).
    """
    if not _refresh_lock.acquire(blocking=False):
        _logger.debug("startup refresh skipped: already in progress")
        return None

    def _run() -> None:
        try:
            run_startup_refresh(project_root)
        finally:
            _refresh_lock.release()

    thread = threading.Thread(target=_run, name="git-it-startup-refresh", daemon=True)
    thread.start()
    return thread
