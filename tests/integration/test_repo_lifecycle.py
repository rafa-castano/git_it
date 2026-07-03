"""Integration tests for the complete repository lifecycle API flow.

These tests exercise the real FastAPI app wired to a real SQLite database.
No mocks of the persistence layer — only the git clone step and background
thread execution are patched (see conftest.py).

Each test gets a fresh SQLite DB via the integration_client fixture and is
fully self-contained with no shared state.
"""

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_INGEST_URL = "https://github.com/test/integration-repo"


def _canonical_repo_id(canonical_url: str) -> str:
    """Mirror the production _canonical_repo_id from repos.py."""
    return "repo-" + hashlib.sha256(canonical_url.encode()).hexdigest()[:12]


_REPO_ID = _canonical_repo_id(_INGEST_URL)


# ---------------------------------------------------------------------------
# 1. test_ingest_and_list
# ---------------------------------------------------------------------------


def test_ingest_and_list(integration_client: TestClient) -> None:
    """Full flow: POST ingest then GET /api/repos → repo appears in list.

    TDD note: passes immediately — the ingest endpoint and list endpoint both
    exist and the mocked ingest correctly writes to the DB.
    """
    resp = integration_client.post("/api/repos/ingest", json={"url": _INGEST_URL})
    assert resp.status_code == 200
    body = resp.json()
    assert body["repository_id"] == _REPO_ID
    assert body["canonical_url"] == _INGEST_URL

    list_resp = integration_client.get("/api/repos")
    assert list_resp.status_code == 200
    list_body = list_resp.json()
    assert list_body["total"] >= 1

    repo_ids = [r["repository_id"] for r in list_body["repos"]]
    assert _REPO_ID in repo_ids

    repo = next(r for r in list_body["repos"] if r["repository_id"] == _REPO_ID)
    assert repo["canonical_url"] == _INGEST_URL
    assert repo["status"] == "COMPLETED"
    assert repo["commit_count"] == 2  # matches FAKE_COMMITS in conftest


# ---------------------------------------------------------------------------
# 2. test_estimate_after_ingest
# ---------------------------------------------------------------------------


def test_estimate_after_ingest(integration_client: TestClient) -> None:
    """Full flow: POST ingest then GET analyze/estimate → expected fields present.

    TDD note: passes immediately — ingest writes commits to DB and estimate
    reads from it; all required response fields come from the existing endpoint.
    """
    integration_client.post("/api/repos/ingest", json={"url": _INGEST_URL})

    resp = integration_client.get(f"/api/repos/{_REPO_ID}/analyze/estimate")
    assert resp.status_code == 200
    body = resp.json()

    # All schema fields must be present
    required_fields = {
        "total_commits",
        "analyzed_commits",
        "unanalyzed_commits",
        "estimated_llm_calls",
        "estimated_analysis_cost_usd",
        "estimated_narrative_cost_usd",
        "estimated_cost_usd",
    }
    assert required_fields.issubset(body.keys())

    # After ingest only — no analysis has run yet
    assert body["total_commits"] == 2  # 2 fake commits
    assert body["analyzed_commits"] == 0
    assert body["unanalyzed_commits"] == 2
    assert body["estimated_llm_calls"] >= 0
    assert body["estimated_cost_usd"] >= 0.0


# ---------------------------------------------------------------------------
# 3. test_commits_after_ingest
# ---------------------------------------------------------------------------


def test_commits_after_ingest(integration_client: TestClient) -> None:
    """Full flow: POST ingest then GET commits → response has correct structure.

    TDD note: passes immediately. The commits endpoint uses an INNER JOIN on
    commit_analyses, so it returns only analyzed commits. After bare ingest
    (no analysis step), the list is empty but the structure is correct.
    """
    integration_client.post("/api/repos/ingest", json={"url": _INGEST_URL})

    resp = integration_client.get(f"/api/repos/{_REPO_ID}/commits")
    assert resp.status_code == 200
    body = resp.json()

    assert "commits" in body
    assert "total" in body
    assert "repository_id" in body
    assert body["repository_id"] == _REPO_ID
    assert isinstance(body["commits"], list)
    assert isinstance(body["total"], int)
    # No analysis has run yet → INNER JOIN on commit_analyses yields 0 rows
    assert body["total"] == 0


# ---------------------------------------------------------------------------
# 4. test_patterns_after_ingest
# ---------------------------------------------------------------------------


def test_patterns_after_ingest(integration_client: TestClient) -> None:
    """Full flow: POST ingest then GET patterns → expected top-level fields present.

    TDD note: passes immediately — pattern detection runs over real DB data and
    returns an empty but structurally valid report for a freshly ingested repo.
    """
    integration_client.post("/api/repos/ingest", json={"url": _INGEST_URL})

    resp = integration_client.get(f"/api/repos/{_REPO_ID}/patterns")
    assert resp.status_code == 200
    body = resp.json()

    assert "hotspots" in body
    assert "bugfix_recurrences" in body
    assert "repository_id" in body
    assert isinstance(body["hotspots"], list)
    assert isinstance(body["bugfix_recurrences"], list)


# ---------------------------------------------------------------------------
# 5. test_contributors_after_ingest
# ---------------------------------------------------------------------------


def test_contributors_after_ingest(integration_client: TestClient) -> None:
    """Full flow: POST ingest then GET contributors → contributors list populated.

    TDD note: passes immediately — the contributors endpoint aggregates from
    commit_facts (not commit_analyses), so it returns real data after ingest.
    """
    integration_client.post("/api/repos/ingest", json={"url": _INGEST_URL})

    resp = integration_client.get(f"/api/repos/{_REPO_ID}/contributors")
    assert resp.status_code == 200
    body = resp.json()

    assert "contributors" in body
    assert "repository_id" in body
    assert isinstance(body["contributors"], list)
    assert len(body["contributors"]) >= 1  # Alice and Bob from FAKE_COMMITS

    first = body["contributors"][0]
    assert "author_name" in first
    assert "commit_count" in first
    assert first["commit_count"] >= 1


# ---------------------------------------------------------------------------
# 6. test_ingest_duplicate
# ---------------------------------------------------------------------------


def test_ingest_duplicate(integration_client: TestClient) -> None:
    """POST ingest twice with same URL → same repository_id (idempotent ID derivation).

    TDD note: passes immediately — repository_id is a deterministic hash of
    the canonical URL. DB writes are idempotent via INSERT OR IGNORE.
    """
    resp1 = integration_client.post("/api/repos/ingest", json={"url": _INGEST_URL})
    resp2 = integration_client.post("/api/repos/ingest", json={"url": _INGEST_URL})

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["repository_id"] == resp2.json()["repository_id"]
    assert resp1.json()["repository_id"] == _REPO_ID


# ---------------------------------------------------------------------------
# 7. test_404_on_unknown_repo
# ---------------------------------------------------------------------------


def test_404_on_unknown_repo(tmp_path: Path) -> None:
    """GET analyze/estimate for an unknown repo (no DB) → 404.

    Uses a fresh client with no ingest so the DB file does not exist at all.
    The analyze/estimate endpoint explicitly returns 404 when db_path is absent.
    TDD note: passes immediately.
    """
    from git_it.api.app import create_app

    app = create_app(project_root=tmp_path)
    # Use raise_server_exceptions=False so 404 is returned normally
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/api/repos/nonexistent-id/analyze/estimate")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 8. test_delete_removes_all_data
# ---------------------------------------------------------------------------


def test_delete_removes_all_data(integration_client: TestClient) -> None:
    """Full flow: ingest → confirm present → DELETE → confirm gone everywhere.

    Spec 008 (repository deletion) is implemented but had no integration-level
    regression test proving deletion actually removes data across the full
    read surface. This test closes that gap.

    Read-surface behavior after delete (verified against the real handlers in
    ``src/git_it/api/routes/repos.py``, not assumed from the spec prose):

    - ``GET /api/repos`` — the repo_id is simply absent from the list.
    - ``GET .../contributors`` — 404, because the handler explicitly raises
      404 when the contributor reader finds no rows (and ``commit_facts``
      rows are deleted by ``SqliteRepositoryDeleter``).
    - ``GET .../case-study`` — 404, same as ``test_404_on_unknown_repo``.
      (This repo never had a narrative generated, so it was already 404
      before delete too — the assertion still documents the contract.)
    - ``GET .../commits`` and ``GET .../patterns`` — these handlers do not
      404 on an unknown/deleted repository_id; they return 200 with empty
      results (0 commits, no hotspots) once ``database_is_provisioned`` is
      True, matching the "empty but structurally valid" behavior already
      exercised by ``test_commits_after_ingest`` / ``test_patterns_after_ingest``.
      This test asserts that actual (empty, not 404) contract rather than the
      404 the spec prose describes for these two routes.

    There is no dedicated single-repo "detail/summary" GET endpoint distinct
    from the list — `GET /api/repos` is the only repo-summary read surface.
    """
    # 1. Ingest and confirm present.
    ingest_resp = integration_client.post("/api/repos/ingest", json={"url": _INGEST_URL})
    assert ingest_resp.status_code == 200

    list_before = integration_client.get("/api/repos")
    assert list_before.status_code == 200
    assert _REPO_ID in [r["repository_id"] for r in list_before.json()["repos"]]

    contributors_before = integration_client.get(f"/api/repos/{_REPO_ID}/contributors")
    assert contributors_before.status_code == 200
    assert len(contributors_before.json()["contributors"]) >= 1  # Alice and Bob

    # 2. Delete.
    delete_resp = integration_client.delete(f"/api/repos/{_REPO_ID}")
    assert delete_resp.status_code == 200
    delete_body = delete_resp.json()
    assert delete_body["deleted"] is True
    assert delete_body["repository_id"] == _REPO_ID

    # 3. Confirm gone across the read surface.
    list_after = integration_client.get("/api/repos")
    assert list_after.status_code == 200
    assert _REPO_ID not in [r["repository_id"] for r in list_after.json()["repos"]]

    contributors_after = integration_client.get(f"/api/repos/{_REPO_ID}/contributors")
    assert contributors_after.status_code == 404

    case_study_after = integration_client.get(f"/api/repos/{_REPO_ID}/case-study")
    assert case_study_after.status_code == 404

    commits_after = integration_client.get(f"/api/repos/{_REPO_ID}/commits")
    assert commits_after.status_code == 200
    assert commits_after.json()["total"] == 0

    patterns_after = integration_client.get(f"/api/repos/{_REPO_ID}/patterns")
    assert patterns_after.status_code == 200
    patterns_body = patterns_after.json()
    assert patterns_body["hotspots"] == []
    assert patterns_body["bugfix_recurrences"] == []
