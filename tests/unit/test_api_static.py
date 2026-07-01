"""Tests for static file serving and root redirect."""

from pathlib import Path

from fastapi.testclient import TestClient

from git_it.api.app import create_app


def test_root_redirects_to_index(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app, follow_redirects=False)
    response = client.get("/")
    assert response.status_code in (301, 302, 307, 308)
    assert "/static/index.html" in response.headers["location"]


def test_static_index_html_served(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app, follow_redirects=True)
    response = client.get("/static/index.html")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Git It" in response.text


def test_static_index_contains_api_calls(tmp_path: Path) -> None:
    # Since batch 76 the JS lives in app.js, not inline in index.html.
    # Verify index.html references the external script and app.js contains the API calls.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    html_response = client.get("/static/index.html")
    assert 'src="/static/app.js"' in html_response.text
    js_response = client.get("/static/app.js")
    assert js_response.status_code == 200
    assert "/api/repos" in js_response.text


def test_openapi_docs_still_available(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/docs")
    assert response.status_code == 200


def test_static_index_contains_chartjs(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/static/index.html")
    assert "chart.js" in response.text.lower() or "Chart" in response.text


def test_static_index_has_four_tabs(tmp_path: Path) -> None:
    # The Deep Analysis panel has four tabs: Overview, Case Study, Commits, Contributors.
    # The Patterns tab was removed in batch 65 (its function still exists in app.js but
    # is no longer exposed as a UI tab). Since batch 76, JS lives in app.js.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/static/index.html")
    for tab in ["Overview", "Case Study", "Commits", "Contributors"]:
        assert tab in response.text


def test_static_index_has_category_colors(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/static/index.html")
    assert "BUGFIX" in response.text or "bugfix" in response.text.lower()


def test_static_index_has_aria_roles(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/static/index.html")
    assert 'role="tablist"' in response.text
    assert 'role="tab"' in response.text
    assert 'role="tabpanel"' in response.text
    assert 'role="tooltip"' in response.text


def test_static_index_has_tooltip_system(tmp_path: Path) -> None:
    # Since batch 76 the JS lives in app.js. The TIPS constant is in app.js;
    # global-tip (the element) and data-tip (attributes) remain in index.html.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    html_response = client.get("/static/index.html")
    assert "global-tip" in html_response.text
    assert "data-tip" in html_response.text
    js_response = client.get("/static/app.js")
    assert js_response.status_code == 200
    assert "TIPS" in js_response.text


def test_static_index_lang_attribute(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/static/index.html")
    assert 'lang="en"' in response.text


# ---------------------------------------------------------------------------
# Spec 012 AC-6 — "Ask" tab (GitItGPT)
# ---------------------------------------------------------------------------


def test_static_index_has_ask_tab(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/static/index.html")
    assert 'data-tab="ask"' in response.text
    assert 'id="tab-ask"' in response.text


def test_static_index_ask_tab_has_input_and_transcript(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/static/index.html")
    assert 'id="ask-input"' in response.text
    assert 'id="ask-transcript"' in response.text
    assert 'id="ask-error"' in response.text


def test_static_app_js_has_chat_submit_logic(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/static/app.js")
    assert response.status_code == 200
    assert "/chat" in response.text
    assert "ask-transcript" in response.text


def test_static_index_ask_tab_has_thinking_indicator(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/static/app.js")
    assert "ask-msg-thinking" in response.text


# ---------------------------------------------------------------------------
# ADR 013 — sanitize all client-side Markdown rendering with DOMPurify
# ---------------------------------------------------------------------------


def test_static_index_loads_dompurify(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/static/index.html")
    assert "dompurify" in response.text.lower()


def test_static_app_js_sanitizes_markdown_via_shared_helper(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/static/app.js")
    text = response.text
    assert "DOMPurify.sanitize(" in text
    # Regression: no call site may bypass the shared helper and render
    # marked.parse() output unsanitized.
    assert "typeof marked !== 'undefined' ? marked.parse" not in text


# ---------------------------------------------------------------------------
# Spec 013 AC-4 — frontend streams the final answer via SSE
# ---------------------------------------------------------------------------


def test_static_app_js_calls_streaming_endpoint(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/static/app.js")
    assert "/chat/stream" in response.text


def test_static_app_js_reads_sse_response_with_silence_timeout(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text
    assert "getReader(" in text
    assert "AbortController" in text
    # Spec 013: 30s of silence is treated as a dropped connection.
    assert "30000" in text


# ---------------------------------------------------------------------------
# Bug fix — Overview charts overflow instead of reflowing when the effective
# viewport narrows (browser zoom or window resize).
#
# Root cause: `.charts-row` is a CSS Grid (`1fr 2fr`); grid items default to
# `min-width: auto`, which floors their shrink at the content's intrinsic size
# — here, the Chart.js `<canvas>`'s last-measured pixel width. Without an
# explicit `min-width: 0` on the grid item, the row cannot shrink below that
# canvas size and instead overflows (content "doesn't adapt"), and once a
# canvas has been pushed into that state it does not reliably self-correct
# when the viewport widens back (content "doesn't restore"). A responsive
# breakpoint stacks the row into one column at narrow effective widths.
# ---------------------------------------------------------------------------


def test_static_app_css_chart_box_can_shrink_below_canvas_intrinsic_size(
    tmp_path: Path,
) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.css").text
    assert ".chart-box { min-width: 0" in text


def test_static_app_css_main_can_shrink_below_content_intrinsic_size(
    tmp_path: Path,
) -> None:
    # Same class of fix, one level up: `main` is a flex item alongside the
    # fixed-width sidebar; without min-width:0 it can't shrink below its
    # widest descendant's intrinsic size either (project-wide audit finding).
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.css").text
    assert "min-width: 0" in text.split("main {", 1)[1].split("}", 1)[0]


def test_static_app_css_has_responsive_breakpoint_for_charts_row(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.css").text
    assert "@media" in text
    assert ".charts-row { grid-template-columns: 1fr" in text
