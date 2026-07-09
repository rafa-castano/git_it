"""Tests for the removal of the manual "Refresh all" home button (spec 033).

Spec 028 shipped a home-view "Refresh all" button (batch 153) that POSTed to
``/api/repos/refresh-all``. Spec 033 replaces the manual trigger with an
automatic, silent, background refresh at server startup (see
``test_startup_refresh.py``) and REMOVES the button and its client handler.

These are pinned regressions that the button and handler are gone. The
``/api/repos/refresh-all`` HTTP endpoint itself is intentionally kept as a
programmatic action (see ``test_api_refresh_all.py``) — only the UI is removed.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from git_it.api.app import create_app


def test_static_app_js_has_no_refresh_all_handler(tmp_path: Path) -> None:
    # Spec 033: the _doRefreshAll client handler is removed with the button.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text
    assert "_doRefreshAll" not in text


def test_static_index_has_no_refresh_all_button(tmp_path: Path) -> None:
    # Spec 033: the button and its status element are removed from the home view.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/index.html").text
    assert 'id="refresh-all-btn"' not in text
    assert 'id="refresh-all-status"' not in text
