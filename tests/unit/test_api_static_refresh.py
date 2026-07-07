"""Tests for the batch 153 "Refresh all" home dashboard button (spec 028).

Spec 028 wires a collection-level "Refresh all" action into the home view:
a button that POSTs to ``/api/repos/refresh-all`` (already shipped in batches
150-152 -- see api/routes/repos.py) and reports a per-repository summary.

These are a pinned regression that the button's frontend wiring exists,
mirroring the batch-148 embedding-backfill button tests
(test_api_static_backfill.py). The real click/result behavior is verified
live via Playwright by the orchestrator, not here.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from git_it.api.app import create_app


def test_static_app_js_has_refresh_all_click_handler_that_posts(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text
    assert "function _doRefreshAll(" in text
    handler_body = text.split("function _doRefreshAll(", 1)[1]
    assert "/api/repos/refresh-all" in handler_body
    assert "method: 'POST'" in handler_body


def test_static_app_js_refresh_all_reloads_repo_list_on_success(tmp_path: Path) -> None:
    # After a successful refresh, the home grid must reflect any new commit
    # counts -- the handler must re-run loadRepos() (which itself triggers
    # renderRepoCards() via the existing home-load path).
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text
    handler_body = text.split("function _doRefreshAll(", 1)[1]
    assert "loadRepos()" in handler_body


def test_static_index_has_refresh_all_button(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/index.html").text
    assert 'id="refresh-all-btn"' in text


def test_static_index_refresh_all_button_calls_click_handler(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/index.html").text
    button_tag = text.split('id="refresh-all-btn"', 1)[1].split(">", 1)[0]
    assert "_doRefreshAll()" in button_tag
