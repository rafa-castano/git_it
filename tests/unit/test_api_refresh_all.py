"""Tests for the refresh-all API endpoint (spec 028, batch 152).

Covers:
- POST /api/repos/refresh-all (collection-level action, no {repository_id})

All tests use FastAPI's TestClient with ``create_app(project_root=tmp_path)`` and a fake
``RefreshAllService`` injected via monkeypatch on ``build_refresh_all_service`` in the
``repos`` route module -- no real git/network calls, mirroring
test_api_backfill.py's ``build_embedding_backfill_service`` injection pattern.
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from git_it.repository_ingestion.application.refresh_all_service import (
    RefreshAllResult,
    RepositoryRefreshResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _db_path(tmp_path: Path) -> Path:
    data_dir = tmp_path / ".data" / "git-it" / "ingestion"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "git-it.sqlite3"


def _provision_db(tmp_path: Path) -> None:
    """Create an empty sqlite file so ``database_is_provisioned`` reports True.

    The refresh-all endpoint's ``database_is_provisioned`` gate only checks file
    existence for the sqlite backend (mirrors ``list_repos``'s own gate) -- the
    real content is irrelevant here since ``build_refresh_all_service`` itself is
    monkeypatched away in these tests.
    """
    db = _db_path(tmp_path)
    with sqlite3.connect(db):
        pass


class _FakeRefreshAllService:
    """Test double for RefreshAllService -- no real ingest, no network."""

    def __init__(self, result: RefreshAllResult) -> None:
        self._result = result

    def refresh_all(self) -> RefreshAllResult:
        return self._result


def _patch_service(monkeypatch: pytest.MonkeyPatch, service: _FakeRefreshAllService) -> None:
    import git_it.api.routes.repos as repos_module

    monkeypatch.setattr(
        repos_module,
        "build_refresh_all_service",
        lambda **kwargs: service,
    )


_TWO_REPO_RESULT = RefreshAllResult(
    repositories=[
        RepositoryRefreshResult(
            repository_id="repo-a",
            canonical_url="https://github.com/test/repo-a",
            status="completed",
            new_commits=3,
        ),
        RepositoryRefreshResult(
            repository_id="repo-b",
            canonical_url="https://github.com/test/repo-b",
            status="failed",
            new_commits=0,
            error_code="FETCH_FAILED",
            safe_message="Refresh failed: ConnectionError",
        ),
    ],
    total_repositories=2,
    refreshed_count=1,
    failed_count=1,
    total_new_commits=3,
)

_EMPTY_RESULT = RefreshAllResult(
    repositories=[],
    total_repositories=0,
    refreshed_count=0,
    failed_count=0,
    total_new_commits=0,
)


# ---------------------------------------------------------------------------
# POST /api/repos/refresh-all -- success mapping
# ---------------------------------------------------------------------------


def test_refresh_all_maps_totals_and_per_repository_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.app import create_app

    _provision_db(tmp_path)
    _patch_service(monkeypatch, _FakeRefreshAllService(_TWO_REPO_RESULT))

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.post("/api/repos/refresh-all")

    assert response.status_code == 200
    body = response.json()
    assert body["total_repositories"] == 2
    assert body["refreshed_count"] == 1
    assert body["failed_count"] == 1
    assert body["total_new_commits"] == 3
    assert len(body["repositories"]) == 2

    repo_a = body["repositories"][0]
    assert repo_a["repository_id"] == "repo-a"
    assert repo_a["canonical_url"] == "https://github.com/test/repo-a"
    assert repo_a["status"] == "completed"
    assert repo_a["new_commits"] == 3
    assert repo_a["error_code"] is None
    assert repo_a["safe_message"] is None

    repo_b = body["repositories"][1]
    assert repo_b["repository_id"] == "repo-b"
    assert repo_b["status"] == "failed"
    assert repo_b["new_commits"] == 0
    assert repo_b["error_code"] == "FETCH_FAILED"
    assert repo_b["safe_message"] == "Refresh failed: ConnectionError"


# ---------------------------------------------------------------------------
# POST /api/repos/refresh-all -- empty case (success, not 404)
# ---------------------------------------------------------------------------


def test_refresh_all_with_nothing_to_refresh_returns_200_zeroed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.app import create_app

    _provision_db(tmp_path)
    _patch_service(monkeypatch, _FakeRefreshAllService(_EMPTY_RESULT))

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.post("/api/repos/refresh-all")

    assert response.status_code == 200
    body = response.json()
    assert body["total_repositories"] == 0
    assert body["refreshed_count"] == 0
    assert body["failed_count"] == 0
    assert body["total_new_commits"] == 0
    assert body["repositories"] == []


def test_refresh_all_with_database_not_provisioned_returns_200_zeroed(
    tmp_path: Path,
) -> None:
    """No sqlite file yet -- mirrors list_repos's own database_is_provisioned gate:
    a success with zero counts, never a 404 (refreshing zero repos is not an error)."""
    from git_it.api.app import create_app

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.post("/api/repos/refresh-all")

    assert response.status_code == 200
    body = response.json()
    assert body["total_repositories"] == 0
    assert body["repositories"] == []


# ---------------------------------------------------------------------------
# POST /api/repos/refresh-all -- auth
# ---------------------------------------------------------------------------


def test_refresh_all_requires_auth_when_api_key_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.app import create_app

    monkeypatch.setenv("GIT_IT_API_KEY", "secret")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.post("/api/repos/refresh-all")
    assert response.status_code == 401


def test_refresh_all_accepts_valid_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from git_it.api.app import create_app

    monkeypatch.setenv("GIT_IT_API_KEY", "secret")
    _provision_db(tmp_path)
    _patch_service(monkeypatch, _FakeRefreshAllService(_EMPTY_RESULT))

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.post(
        "/api/repos/refresh-all",
        headers={"Authorization": "Bearer secret"},
    )
    assert response.status_code != 401


# ---------------------------------------------------------------------------
# Routing safety: literal /refresh-all must not be shadowed by {repository_id}
# ---------------------------------------------------------------------------


def test_refresh_all_route_reaches_refresh_handler_not_a_param_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proves POST /api/repos/refresh-all resolves to the refresh-all handler and not
    some other {repository_id}-shaped handler treating "refresh-all" as an id -- the
    response must have the refresh-all aggregate shape (total_repositories/
    refreshed_count/failed_count/total_new_commits/repositories), not a 404/other shape."""
    from git_it.api.app import create_app

    _provision_db(tmp_path)
    _patch_service(monkeypatch, _FakeRefreshAllService(_TWO_REPO_RESULT))

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.post("/api/repos/refresh-all")

    assert response.status_code == 200
    body = response.json()
    assert body["total_repositories"] == 2
    assert set(body.keys()) == {
        "total_repositories",
        "refreshed_count",
        "failed_count",
        "total_new_commits",
        "repositories",
    }
