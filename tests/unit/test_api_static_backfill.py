"""Tests for the batch 148 embedding-backfill dashboard button (spec 027).

These are a pinned regression that the button's frontend wiring exists and is
gated the way spec 027's "Dashboard control visibility" acceptance criterion
requires (shown only when `available` AND `missing > 0`). The real click/poll
behavior is verified live via Playwright by the orchestrator, not here.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from git_it.api.app import create_app


def test_static_app_js_wires_backfill_status_endpoint(tmp_path: Path) -> None:
    # The repo detail header must fetch the GET status endpoint to decide
    # whether to show the button at all.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text
    assert "/backfill-embeddings" in text
    assert "function _loadBackfillStatus(" in text


def test_static_app_js_gates_backfill_button_on_available_and_missing(tmp_path: Path) -> None:
    # Spec 027 acceptance criterion "Dashboard control visibility": shown only
    # when available AND missing > 0; hidden otherwise. Pinned as one literal
    # condition so a regression that drops either half of the AND is caught.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text
    assert "status.available && status.missing > 0" in text


def test_static_app_js_has_backfill_click_handler_that_posts(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text
    assert "function _doBackfillEmbeddings(" in text
    handler_body = text.split("function _doBackfillEmbeddings(", 1)[1]
    assert "/backfill-embeddings" in handler_body
    assert "method: 'POST'" in handler_body


def test_static_app_js_handles_no_key_503_response(tmp_path: Path) -> None:
    # Failure mode: no OPENAI_API_KEY -> 503. Must not be treated as a
    # generic error; the button should re-hide/explain rather than alarm.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text
    handler_body = text.split("function _doBackfillEmbeddings(", 1)[1]
    assert "503" in handler_body


def test_static_index_has_backfill_button_hidden_by_default(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/index.html").text
    assert 'id="sh-backfill-btn"' in text
    button_tag = text.split('id="sh-backfill-btn"', 1)[1].split(">", 1)[0]
    assert "display:none" in button_tag or "display: none" in button_tag


def test_static_index_backfill_button_calls_click_handler(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/index.html").text
    button_tag = text.split('id="sh-backfill-btn"', 1)[1].split(">", 1)[0]
    assert "_doBackfillEmbeddings()" in button_tag
