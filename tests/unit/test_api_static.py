"""Tests for static file serving and root redirect."""

import re
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


def test_static_app_js_has_category_colors(tmp_path: Path) -> None:
    # Batch 127: the category filter/legend chips are generated dynamically in
    # app.js (CAT_COLORS/_COMMIT_CATEGORIES), same as the donut's own legend
    # always was — index.html no longer hardcodes category <option>s.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/static/app.js")
    assert "BUGFIX" in response.text


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


def test_static_app_css_scrollbars_are_theme_aware(tmp_path: Path) -> None:
    # Dark mode: the app never styled scrollbars, so they fell back to the UA
    # default (light-gray track/thumb) that ignored the theme — visible in the
    # Ask tab after several exchanges. Now themed via theme vars so both
    # scrollbar-color (Firefox) and ::-webkit-scrollbar (Chromium/WebKit) read
    # --border/--muted and adapt to the [data-theme="light"] override for free.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.css").text
    assert "scrollbar-color: var(--muted) transparent" in text
    thumb = text.split("::-webkit-scrollbar-thumb {", 1)[1].split("}", 1)[0]
    assert "background: var(--muted)" in thumb
    assert "border-radius" in thumb


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
        ".tl-day-sep {",
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


def test_static_app_css_dark_mode_links_use_lighter_blue(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.css").text
    root_rule = text.split(":root {", 1)[1].split("}", 1)[0]
    light_rule = text.split('[data-theme="light"] {', 1)[1].split("}", 1)[0]
    assert "--link: #93c5fd;" in root_rule
    assert "--link: #2563eb;" in light_rule
    for rule_prefix in [
        ".rc-open-btn {",
        ".overview-cs-link {",
        ".case-study-meta a {",
        ".markdown-body a {",
        ".cc-gh-link {",
    ]:
        rule = text.split(rule_prefix, 1)[1].split("}", 1)[0]
        assert "color: var(--link)" in rule


# ---------------------------------------------------------------------------
# Dark-mode contrast audit, round 4 — two hardcoded colors that never went
# through a CSS variable (so earlier rounds' fixes couldn't reach them), plus
# a general typography bump ("too small at 100% zoom").
# ---------------------------------------------------------------------------


def test_static_app_js_chart_tick_colors_read_css_variables(tmp_path: Path) -> None:
    # loadOverview() had its own _tc/_tcy/_gc helpers hardcoding theme hex
    # values directly (e.g. dark tick color '#94a3b8', independent of
    # --muted), instead of reading the CSS variables like the other chart's
    # helpers already did. Any future --muted/--text/--border brightening
    # would silently miss this chart's axis labels, exactly as happened here.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text
    assert text.count("getComputedStyle(document.documentElement).getPropertyValue('--muted')") >= 2
    assert "document.documentElement.dataset.theme === 'light' ? '#475569' : '#94a3b8'" not in text


def test_static_app_css_cs_tl_sub_dot_has_visible_background(tmp_path: Path) -> None:
    # .cs-tl-sub-dot used background: var(--bg) — identical to the page's
    # own background — so the icon circle had no visible backdrop, only its
    # 1px border. Matches .cs-tl-dot's already-correct var(--surface).
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.css").text
    rule = text.split(".cs-tl-sub-dot {", 1)[1].split("}", 1)[0]
    assert "background:var(--surface)" in rule


def test_static_app_css_font_sizes_bumped_up_for_legibility(tmp_path: Path) -> None:
    # "Too small in 100% zoom" — the app was dominated by 10-13px text with
    # almost nothing above 14px. Every literal `font-size: Npx` declaration
    # (rem/em-based sizes were left alone) was bumped by +1px.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.css").text
    assert "body { font-family: 'Inter', system-ui, sans-serif; font-size: 16px;" in text
    # The smallest labels/badges (originally 10px) should now be 11px, not 10px.
    assert re.search(r"font-size:\s?10px", text) is None


def test_static_app_css_repo_card_stats_dont_break_mid_phrase(tmp_path: Path) -> None:
    # Bumping font-size pushed "<strong>1548</strong> commits" past the
    # repo-card's width, wrapping mid-phrase ("1548" / "commits" on separate
    # lines). .rc-stat now stays on one line as a unit; the row as a whole
    # wraps instead, keeping each stat phrase intact.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.css").text
    stats_rule = text.split(".rc-stats {", 1)[1].split("}", 1)[0]
    assert "flex-wrap: wrap" in stats_rule
    stat_rule = text.split(".rc-stat {", 1)[1].split("}", 1)[0]
    assert "white-space: nowrap" in stat_rule


def test_static_app_js_refreshes_current_repo_meta_after_analysis(tmp_path: Path) -> None:
    # Regression: when analysis finishes, the top-bar "N analyzed" pill must
    # stop reading stale currentRepoMeta from the initial /api/repos load.
    # The completion flow should refresh /api/repos-derived metadata for the
    # open repo, then re-render the detail header from that fresh metadata.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text

    assert "async function refreshCurrentRepoMeta(" in text
    assert "function renderHeaderRepoMeta(" in text

    poll_body = text.split("function _pollAnalyzeStatus(repoId)", 1)[1]
    on_done_body = poll_body.split("onDone:", 1)[1].split("onError:", 1)[0]
    assert "await refreshCurrentRepoMeta(repoId)" in on_done_body
    assert "renderHeaderRepoMeta()" in on_done_body


def test_static_app_js_delete_repo_refreshes_sidebar_from_cache(tmp_path: Path) -> None:
    # Regression: deleting from the home cards removed the card and updated
    # reposCache, but left the already-rendered sidebar DOM stale. Selecting
    # another repo then still showed the deleted repository in the sidebar.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text

    assert "function renderSidebarRepos()" in text

    delete_success_body = text.split("if (res.ok) {", 1)[1].split(
        "} else if (res.status === 409)",
        1,
    )[0]
    assert "reposCache = reposCache.filter(r => r.repository_id !== repoId)" in delete_success_body
    assert "renderSidebarRepos()" in delete_success_body


def test_static_app_marks_analysis_updated_tabs_until_opened(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text

    assert "const UPDATED_ANALYSIS_TABS = new Set(['overview', 'case-study', 'commits'])" in text
    assert "function markUpdatedTabs(tabIds)" in text
    assert "function clearUpdatedTab(tabId)" in text
    assert "function renderUpdatedTabIndicators()" in text

    poll_body = text.split("function _pollAnalyzeStatus(repoId)", 1)[1]
    on_done_body = poll_body.split("onDone:", 1)[1].split("onError:", 1)[0]
    assert "markUpdatedTabs(['overview', 'case-study', 'commits'])" in on_done_body

    switch_tab_body = text.split("function switchTab(tabName)", 1)[1].split(
        "function markUpdatedTabs(tabIds)",
        1,
    )[0]
    assert "clearUpdatedTab(tabName)" in switch_tab_body

    select_repo_body = text.split("function selectRepo(repoId)", 1)[1].split(
        "/* =========================================================\n   Timeline",
        1,
    )[0]
    assert "clearUpdatedTabs()" in select_repo_body


def test_static_app_refreshes_overview_after_analysis_completion(tmp_path: Path) -> None:
    # Regression: the green dot proved the analysis onDone flow ran, but Overview
    # was only marked as updated; its charts stayed stale/empty until manual reload.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text

    poll_body = text.split("function _pollAnalyzeStatus(repoId)", 1)[1]
    on_done_body = poll_body.split("onDone:", 1)[1].split("onError:", 1)[0]
    assert "if (currentRepo === repoId) loadOverview(repoId)" in on_done_body


def test_static_app_has_analyze_stop_button_and_cancel_endpoint(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    html = client.get("/static/index.html").text
    js = client.get("/static/app.js").text

    assert 'id="sh-analyze-stop-btn"' in html
    assert 'onclick="_cancelAnalyze()"' in html
    assert "async function _cancelAnalyze()" in js
    assert "/analyze/cancel" in js
    assert "res.status === 409" in js
    assert "Stopping…" in js
    assert "cancel_requested" in js


def test_static_app_cancelled_analysis_refreshes_only_overview_and_commits(
    tmp_path: Path,
) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text

    poll_body = text.split("function _pollAnalyzeStatus(repoId)", 1)[1]
    cancelled_body = poll_body.split("if (finalStatus?.cancelled)", 1)[1].split(
        "return;",
        1,
    )[0]
    assert "loadTimeline(repoId)" in cancelled_body
    assert "loadOverview(repoId)" in cancelled_body
    assert "markUpdatedTabs(['overview', 'commits'])" in cancelled_body
    assert "loadCaseStudy(repoId)" not in cancelled_body
    assert "markUpdatedTabs(['overview', 'case-study', 'commits'])" not in cancelled_body


def test_static_app_css_has_updated_tab_dot_indicator(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.css").text

    assert ".tab-btn.is-updated::after" in text
    rule = text.split(".tab-btn.is-updated::after {", 1)[1].split("}", 1)[0]
    assert 'content: ""' in rule
    assert "border-radius: 999px" in rule
    assert "background: var(--green)" in rule


def test_static_app_js_linkify_commit_shas_is_tag_aware(tmp_path: Path) -> None:
    # Batch 156, bug 2: a blind whole-string replace injected an <a> into tag
    # attribute values (e.g. a timeline node's title="...c0dab29..."), corrupting the
    # markup. _linkifyCommitShas must now split on tags so attributes are never touched.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text

    # New tag-aware split: match a whole tag OR a run of non-tag text, and only
    # linkify inside the non-tag text segments.
    assert "/<[^>]*>|[^<]+/g" in text
    # The old blind whole-string replace with the href-only lookbehind must be gone.
    assert "(?<!href=" not in text


def test_static_app_js_linkable_path_requires_a_slash(tmp_path: Path) -> None:
    # Batch 156, bug 3: linking a bare basename like `ports.py` blindly to
    # /blob/<branch>/ports.py 404s when the real file is nested. isLinkablePath itself
    # still gates the SLASHED-path branch on a separator. Spec 032 handles bare basenames
    # separately in _linkifyPaths (safe, via unique tree resolution) — NOT by relaxing
    # this predicate.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text

    body = text.split("function isLinkablePath(text) {", 1)[1].split("}", 1)[0]
    assert "hasSlash || hasKnownExtension" not in body
    assert "text.includes('/')" in body


def test_static_app_js_arch_pattern_highlight_excludes_engineering_lessons(
    tmp_path: Path,
) -> None:
    # Batch 156, bug 4: Engineering Lessons point 7 ("Streaming Changes the Architecture...")
    # matched /architect/i and was wrongly highlighted as an architectural-pattern card.
    # The highlight is now scoped out of the 'Engineering Lessons' section.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text

    # loadCaseStudy passes the section title through to _renderSectionCards.
    assert "_renderSectionCards(s.content, s.title)" in text
    # The isArchPattern computation is gated by the section title.
    assert "sectionTitle !== 'Engineering Lessons'" in text


def test_static_app_js_linkify_paths_takes_file_path_set(tmp_path: Path) -> None:
    # Spec 029 AC-06/AC-07: _linkifyPaths now receives the repo's verified
    # file-path Set as a fourth argument, and an empty/absent set disables linking.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text

    assert "function _linkifyPaths(html, canonicalUrl, defaultBranch, filePathSet)" in text
    # AC-07: no set (or empty) => html returned unchanged, no links.
    assert "if (!filePathSet || filePathSet.size === 0) return html;" in text


def test_static_app_js_linkify_paths_verifies_against_tree(tmp_path: Path) -> None:
    # Spec 029 AC-06: a file span must be an EXACT member of the set; a folder
    # span must be a directory prefix of at least one member. Unverified => plain.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text

    verify = text.split("function _verifyTreePath(text, filePathSet) {", 1)[1].split(
        "\n}",
        1,
    )[0]
    # Exact set membership => 'file'.
    assert "filePathSet.has(text)" in verify
    assert "return 'file';" in verify
    # Directory prefix of a member => 'folder' (trailing-slash spans reuse the prefix).
    assert "text.endsWith('/') ? text : `${text}/`" in verify
    assert "member.startsWith(prefix)" in verify
    assert "return 'folder';" in verify

    # _linkifyPaths only links when _verifyTreePath returns a kind; else plain code.
    linkify = text.split("function _linkifyPaths(", 1)[1]
    assert "kind = _verifyTreePath(text, filePathSet);" in linkify
    assert "if (!kind) return match;" in linkify


def test_static_app_js_linkify_paths_shows_basename_with_full_path_title(
    tmp_path: Path,
) -> None:
    # Spec 029 AC-06/§12: visible text is the basename, the full path goes in
    # title=, and BOTH are escaped via esc() (escaping must not be weakened).
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text

    basename = text.split("function _pathBasename(path) {", 1)[1].split("\n}", 1)[0]
    assert "segments[segments.length - 1]" in basename
    # Trailing slash preserved so `tests/` still reads as `tests/`.
    assert "path.endsWith('/') ? `${last}/` : last;" in basename

    # The anchor renders the escaped basename as text and the escaped full path in title=.
    # Spec 032: both derive from the resolved full path (linkPath), not the raw span text,
    # so a bare-basename span shows its verified full path in title=.
    assert 'title="${esc(linkPath)}"' in text
    assert "${esc(_pathBasename(linkPath))}</a>" in text


def test_static_app_js_fetches_and_caches_file_paths_per_repo(tmp_path: Path) -> None:
    # Spec 029: the file-path set is fetched lazily from /file-paths once per repo
    # and cached client-side keyed by repository id (no refetch on re-render).
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text

    assert "/file-paths" in text
    loader = text.split("async function _loadFilePathSet(repoId) {", 1)[1].split(
        "\n}",
        1,
    )[0]
    # Return the cached set if already loaded (per-repo cache, no refetch).
    assert "if (_filePathSetCache[repoId]) return _filePathSetCache[repoId];" in loader
    assert "await apiFetch(`/api/repos/${encodeURIComponent(repoId)}/file-paths`)" in loader
    assert "new Set(paths)" in loader
    assert "_filePathSetCache[repoId] = set;" in loader
    # loadCaseStudy awaits the set and passes it into _linkifyPaths.
    assert "const filePathSet = await _loadFilePathSet(repoId);" in text


def test_static_app_js_basename_index_keys_only_extensioned_and_marks_ambiguous(
    tmp_path: Path,
) -> None:
    # Spec 032 AC-01/AC-02/AC-04/AC-08: _basenameIndex maps basename -> full path, built
    # once from the verified tree. Only basenames containing '.' (extensioned files) are
    # indexed (tool/function names and bare folder words are excluded), and a basename
    # shared by two-or-more members is marked ambiguous (null sentinel).
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text

    assert "function _basenameIndex(filePathSet) {" in text
    index = text.split("function _basenameIndex(filePathSet) {", 1)[1].split("\n}", 1)[0]
    # Basename is the last path segment.
    assert "member.split('/').pop()" in index
    # Only extensioned basenames are indexed.
    assert "base.includes('.')" in index
    # Second occurrence => ambiguity sentinel (null); first => the full path.
    assert "index.set(base, null)" in index
    assert "index.set(base, member)" in index


def test_static_app_js_resolve_unique_basename_only_for_no_slash_unique(
    tmp_path: Path,
) -> None:
    # Spec 032 AC-01/AC-02/AC-03: _resolveUniqueBasename returns the full path only for a
    # no-slash span mapped to a non-null (unique) value; null for slashed, unknown, or
    # ambiguous spans.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text

    assert "function _resolveUniqueBasename(text, basenameIndex) {" in text
    resolve = text.split("function _resolveUniqueBasename(text, basenameIndex) {", 1)[1].split(
        "\n}", 1
    )[0]
    # A slashed span is never resolved here (that is the spec-029 branch).
    assert "if (text.includes('/')) return null;" in resolve
    # Only a unique (string) mapping resolves; the ambiguity sentinel (null) does not.
    assert "typeof resolved === 'string' ? resolved : null" in resolve


def test_static_app_js_linkify_paths_resolves_bare_basename_as_file(
    tmp_path: Path,
) -> None:
    # Spec 032 AC-01/AC-05/AC-06/AC-08: _linkifyPaths builds the basename index ONCE
    # (outside replace), branches slashed->_verifyTreePath vs bare->_resolveUniqueBasename
    # (kind='file'), and always feeds the RESOLVED full path (linkPath) into the URL —
    # never the raw span.
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    text = client.get("/static/app.js").text

    linkify = text.split("function _linkifyPaths(", 1)[1].split("\nfunction ", 1)[0]
    # Index built once, before the replace loop.
    assert "const basenameIndex = _basenameIndex(filePathSet);" in linkify
    assert linkify.index("_basenameIndex(filePathSet)") < linkify.index(".replace(")
    # Bare-basename branch resolves to a file link.
    assert "linkPath = _resolveUniqueBasename(text, basenameIndex);" in linkify
    assert "if (!linkPath) return match;" in linkify
    assert "kind = 'file';" in linkify
    # The resolved path (not the raw span) is charset-revalidated and fed to the URL.
    assert "if (!_isSafePathLikeString(linkPath)) return match;" in linkify
    assert "_pathToGithubUrl(linkPath, canonicalUrl, defaultBranch, kind)" in linkify
