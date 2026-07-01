"""Tests for static file serving and root redirect."""

from pathlib import Path

import pytest
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


def test_static_app_css_repo_card_shadow_has_light_theme_override(tmp_path: Path) -> None:
    # a11y audit finding: .repo-card's dark rgba(0,0,0,0.3) shadow had no
    # [data-theme="light"] override, unlike .stat-card/.chart-box which
    # already supply a lighter rgba(0,0,0,0.06) for light mode.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.css").text
    assert '[data-theme="light"] .repo-card { box-shadow: 0 1px 3px rgba(0,0,0,0.06); }' in text


def test_static_app_css_hdr_status_centers_its_text(tmp_path: Path) -> None:
    # .hdr-meta is a flex row with default align-items:stretch, so .hdr-status
    # gets stretched to match its taller siblings (buttons); without its own
    # centering the text sits top-aligned in the stretched pill instead of centered.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.css").text
    rule = text.split(".hdr-status {", 1)[1].split("}", 1)[0]
    assert "display: flex" in rule
    assert "align-items: center" in rule
    assert "justify-content: center" in rule


def test_static_app_css_tl_day_sep_is_visually_prominent(tmp_path: Path) -> None:
    # The day separator in the Commits tab used var(--border) text on a
    # 2rem partial line — nearly invisible against the background. Now
    # uses a tinted band with a full-width accent line for visual prominence;
    # the text itself is var(--text) (see the dark-mode contrast audit
    # tests below) since even a lightened accent still read as "blue text".
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.css").text
    rule = text.split(".tl-day-sep {", 1)[1].split("}", 1)[0]
    assert "color: var(--text)" in rule
    assert "background: color-mix(in srgb, var(--accent)" in rule


def test_static_app_js_day_groups_default_closed_and_toggle(tmp_path: Path) -> None:
    # Commits tab: day blocks render closed by default; clicking the day
    # separator (tlDayToggle) rolls them out. Mirrors the existing tlToggle
    # pattern used for individual commit detail rows.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text
    assert "function tlDayToggle(id)" in text
    assert 'onclick="tlDayToggle(' in text
    assert "class=\"tl-day-group${openNow ? ' open' : ''}\"" in text
    assert "aria-expanded=\"${openNow ? 'true' : 'false'}\"" in text


def test_static_app_js_active_filter_expands_day_groups(tmp_path: Path) -> None:
    # Closed-by-default day groups must not hide search/filter results — a
    # narrowing filter (keyword/date range/category/evidence/hour) forces
    # defaultOpen so matches are visible without an extra click per day.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text
    assert "renderTimeline(commits, _tlPatterns, { defaultOpen: hasActiveFilter })" in text


def test_static_app_css_tl_day_group_closed_by_default(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.css").text
    assert ".tl-day-group { display: none; }" in text
    assert ".tl-day-group.open { display: block; }" in text
    assert '.tl-day-sep[aria-expanded="true"] .tl-day-chevron { transform: rotate(90deg); }' in text


def test_static_app_js_overview_activity_chart_shows_commits_empty_state(tmp_path: Path) -> None:
    # Selecting a date range with no commits in the Overview tab's Commit
    # Activity chart previously left the stale/blank chart on screen with no
    # feedback. Now it shows the same empty state as the Commits tab, and
    # restores the canvas + chart when the range is widened/cleared again.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text
    assert 'id="chart-activity-container"' in text
    assert "if (!actLabels.length) {" in text
    section = text.split("if (!actLabels.length) {", 1)[1].split("return;", 1)[0]
    assert "No analyzed commits yet." in section
    assert "Use the <strong>+ Analyze</strong> button above to start commit analysis." in section
    assert "if (container && !document.getElementById('chart-activity'))" in text


# ---------------------------------------------------------------------------
# Dark-mode contrast audit (frontend-a11y skill) — var(--border) (#2d3148)
# was being reused as TEXT color for separator characters, giving ~1.3:1-1.5:1
# contrast against --bg/--surface (WCAG requires >=4.5:1 for body text, or
# >=3:1 even for large/UI text). --muted (#9ca3af) gives ~6.6:1-7.4:1.
# ---------------------------------------------------------------------------


def test_static_app_css_separators_use_muted_not_border_for_text(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.css").text
    assert ".hdr-sep { color: var(--muted); }" in text
    assert ".tl-timeframe-sep { color: var(--muted); }" in text
    assert "color: var(--border)" not in text
    assert "color:var(--border)" not in text


def test_static_app_js_separators_use_muted_not_border_for_text(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text
    assert "color:var(--border)" not in text


def test_static_index_html_hdr_sep_has_no_low_contrast_inline_override(tmp_path: Path) -> None:
    # The .hdr-sep CSS rule alone wasn't enough — index.html had an inline
    # style="color:var(--border)" on the same element, which wins on
    # specificity and silently defeated the CSS fix above.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/index.html").text
    assert 'class="hdr-sep"' in text
    assert "color:var(--border)" not in text
    assert "color: var(--border)" not in text


def test_static_app_css_ask_error_uses_dark_mode_appropriate_colors(tmp_path: Path) -> None:
    # #ask-error's default (dark-mode) rule shipped a light-mode-appropriate
    # palette (light pink bg + dark red text) with only [data-theme="light"]
    # overriding it to a *different* light palette — dark mode never had its
    # own colors. Now the default matches the dark-tinted-bg + light-text
    # convention already used by .badge-bugfix etc.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.css").text
    assert "#ask-error { background: #3f1d1d; color: #fca5a5;" in text
    assert '[data-theme="light"] #ask-error { background: #fef2f2; color: #b91c1c;' in text


# ---------------------------------------------------------------------------
# Dark-mode contrast audit, round 2 (superseded — see round 3 below) — tried
# brightening --accent to a lighter #818cf8 ("--accent-text") for small/body
# text instead of using --accent (#6366f1, 4.22:1 on --bg, below the 4.5:1
# WCAG AA minimum). Users still reported it as "dark blue text" — a lighter
# step of the same hue is still categorically blue. Round 3 replaces all of
# it with var(--text) (no blue at all), keeping --accent only for
# backgrounds/borders/underlines where color signals "active" without the
# text itself needing to be legible-as-blue.
#
# Round 3 also keeps: unstyled ::placeholder fell back to the browser default
# gray (~#757575, ~3.65:1 on dark inputs) instead of the theme.
# ---------------------------------------------------------------------------


def test_static_app_css_placeholder_uses_muted_not_browser_default(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.css").text
    assert "::placeholder { color: var(--muted); opacity: 1; }" in text


def test_static_app_css_no_leftover_accent_text_variable(tmp_path: Path) -> None:
    # Round 2 introduced --accent-text as a lighter shade of --accent for
    # text; round 3 replaced every usage with var(--text) instead, so the
    # variable should not still be defined as dead code.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.css").text
    assert "accent-text" not in text


@pytest.mark.parametrize(
    "rule_prefix",
    [
        ".rc-open-btn {",
        ".tl-day-sep {",
        ".overview-cs-link {",
        ".case-study-meta a {",
        ".cs-arch-pattern-card .cs-subcard-title {",
        ".cc-rank {",
        ".contributors-top-label {",
        ".analyze-btn {",
        ".cs-tl-label-cnt {",
        ".migration-row .arrow {",
    ],
)
def test_static_app_css_small_text_uses_text_not_accent(tmp_path: Path, rule_prefix: str) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.css").text
    assert rule_prefix in text, f"rule {rule_prefix!r} not found in app.css"
    rule = text.split(rule_prefix, 1)[1].split("}", 1)[0]
    assert "color: var(--text)" in rule or "color:var(--text)" in rule
    assert "color: var(--accent);" not in rule
    assert "color:var(--accent);" not in rule


def test_static_app_css_tab_active_states_use_text_for_color_only(
    tmp_path: Path,
) -> None:
    # .tab-btn / .cs-tab-btn active states set both color and border-bottom-color
    # to accent originally — the text color is now var(--text) (no blue at
    # all); the border-bottom stays --accent as the "this tab is active"
    # visual cue, which doesn't need to be legible text.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.css").text
    tab_rule = text.split('.tab-btn[aria-selected="true"] {', 1)[1].split("}", 1)[0]
    assert "color: var(--text)" in tab_rule
    assert "border-bottom-color: var(--accent)" in tab_rule
    cs_tab_rule = text.split(".cs-tab-btn.active {", 1)[1].split("}", 1)[0]
    assert "color: var(--text)" in cs_tab_rule
    assert "border-bottom-color: var(--accent)" in cs_tab_rule


def test_static_app_js_links_and_buttons_use_text_not_accent(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text
    assert "color:var(--accent);" not in text
    assert "color: var(--accent);" not in text
    assert "accent-text" not in text
    assert text.count("color:var(--text);text-decoration:underline") >= 3


def test_static_app_css_muted_is_brightened_for_legibility(tmp_path: Path) -> None:
    # --muted (#9ca3af, ~7.4:1 on --bg) technically passed WCAG AA, but users
    # reported it as too dim next to full-brightness --text in side-by-side
    # contexts (active vs. inactive tabs, etc.) — same lesson as --accent:
    # pick a clearly brighter step, not a marginal one. Only dark mode was
    # reported as dim; light mode's --muted is unchanged.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.css").text
    root_rule = text.split(":root {", 1)[1].split("}", 1)[0]
    light_rule = text.split('[data-theme="light"] {', 1)[1].split("}", 1)[0]
    assert "--muted: #c1c9d6;" in root_rule
    assert "--muted: #475569;" in light_rule
