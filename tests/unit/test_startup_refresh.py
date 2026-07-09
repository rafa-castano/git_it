"""Tests for spec 033: automatic silent background refresh on server startup.

The refresh runs off the request path in a daemon thread, is failure-isolated,
single-flight, and opt-in (only the served module-level app enables it). The
underlying ``run_startup_refresh`` body is tested synchronously (no threads);
``start_background_refresh`` is tested for thread/daemon/single-flight behavior;
the lifespan wiring is tested through ``create_app``.
"""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from git_it.api import startup as startup_mod
from git_it.api.app import create_app
from git_it.repository_ingestion.application.refresh_all_service import RefreshAllResult


class _FakeService:
    def __init__(self) -> None:
        self.calls = 0

    def refresh_all(self) -> RefreshAllResult:
        self.calls += 1
        return RefreshAllResult(
            repositories=[],
            total_repositories=0,
            refreshed_count=0,
            failed_count=0,
            total_new_commits=0,
        )


# ---------------------------------------------------------------------------
# run_startup_refresh — synchronous body (AC-01 body / AC-04 / AC-06)
# ---------------------------------------------------------------------------


def test_run_startup_refresh_calls_refresh_all_when_provisioned(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _FakeService()
    monkeypatch.setattr(startup_mod, "database_is_provisioned", lambda *, project_root: True)
    monkeypatch.setattr(startup_mod, "build_refresh_all_service", lambda *, project_root: fake)
    startup_mod.run_startup_refresh(tmp_path)
    assert fake.calls == 1


def test_run_startup_refresh_skips_when_db_not_provisioned(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    built: list[int] = []
    monkeypatch.setattr(startup_mod, "database_is_provisioned", lambda *, project_root: False)
    monkeypatch.setattr(
        startup_mod, "build_refresh_all_service", lambda *, project_root: built.append(1)
    )
    startup_mod.run_startup_refresh(tmp_path)
    assert built == []  # AC-06: service never built when the DB is not provisioned


def test_run_startup_refresh_swallows_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _boom(*, project_root: Path) -> object:
        # The message would carry a tokened URL in the wild; it must never surface.
        raise RuntimeError("token=SECRET https://x@github.com/o/r.git")

    monkeypatch.setattr(startup_mod, "database_is_provisioned", lambda *, project_root: True)
    monkeypatch.setattr(startup_mod, "build_refresh_all_service", _boom)
    # AC-04: must not raise.
    startup_mod.run_startup_refresh(tmp_path)


# ---------------------------------------------------------------------------
# start_background_refresh — thread / daemon / single-flight (AC-01/02/05)
# ---------------------------------------------------------------------------


def test_start_background_refresh_spawns_daemon_thread(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _FakeService()
    monkeypatch.setattr(startup_mod, "database_is_provisioned", lambda *, project_root: True)
    monkeypatch.setattr(startup_mod, "build_refresh_all_service", lambda *, project_root: fake)
    thread = startup_mod.start_background_refresh(tmp_path)
    assert thread is not None
    assert thread.daemon is True  # AC-02: never blocks process shutdown
    thread.join(timeout=5)
    assert fake.calls == 1  # AC-01: refresh ran in the thread


def test_start_background_refresh_is_single_flight(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _FakeService()
    monkeypatch.setattr(startup_mod, "database_is_provisioned", lambda *, project_root: True)
    monkeypatch.setattr(startup_mod, "build_refresh_all_service", lambda *, project_root: fake)
    # Hold the guard lock => a start request must be a no-op (AC-05).
    assert startup_mod._refresh_lock.acquire(blocking=False) is True
    try:
        thread = startup_mod.start_background_refresh(tmp_path)
        assert thread is None
        assert fake.calls == 0
    finally:
        startup_mod._refresh_lock.release()


# ---------------------------------------------------------------------------
# project_root resolution (AC-08)
# ---------------------------------------------------------------------------


def test_resolve_startup_project_root_prefers_explicit(tmp_path: Path) -> None:
    assert startup_mod.resolve_startup_project_root(tmp_path) == tmp_path


def test_resolve_startup_project_root_falls_back_to_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GIT_IT_DATA_DIR", str(tmp_path))
    assert startup_mod.resolve_startup_project_root(None) == tmp_path


def test_resolve_startup_project_root_falls_back_to_cwd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GIT_IT_DATA_DIR", raising=False)
    assert startup_mod.resolve_startup_project_root(None) == Path(os.getcwd())


# ---------------------------------------------------------------------------
# Lifespan wiring via create_app (AC-01 trigger / AC-03 default-off)
# ---------------------------------------------------------------------------


def test_create_app_triggers_startup_refresh_when_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[Path] = []
    monkeypatch.setattr(
        startup_mod, "start_background_refresh", lambda project_root: calls.append(project_root)
    )
    app = create_app(project_root=tmp_path, enable_startup_refresh=True)
    with TestClient(app):  # entering the context runs the startup lifespan
        pass
    assert calls == [tmp_path]


def test_create_app_does_not_trigger_startup_refresh_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[Path] = []
    monkeypatch.setattr(
        startup_mod, "start_background_refresh", lambda project_root: calls.append(project_root)
    )
    app = create_app(project_root=tmp_path)  # AC-03: default is off
    with TestClient(app):
        pass
    assert calls == []
