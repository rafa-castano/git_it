# Batch 64 — UI/UX overhaul: 11 fixes including design polish, timeline filters, and Case Study improvements

## Goal

Apply 11 targeted UI/UX fixes to `src/git_it/static/index.html`, covering functional bugs, design polish, and information architecture improvements. A new `award-winning-dev-tool-design` skill was created beforehand from research into Linear, Vercel, Railway, and Raycast design systems.

## Changes Made

### Fix 1 — Analysis count doesn't update after analysis ends

In `_pollAnalyzeStatus()`, after `clearInterval(intervalId)` when analysis completes, the code now:
- Fetches the updated estimate from the API
- Updates `#sh-analyzed` with the new count
- Reloads the commits tab if it's currently active

### Fix 2 — Timeline limit selector doesn't change commit count

In `_applyTimelineFilters()`, the logic was inverted: it re-fetched when `limit < cached`, meaning going 100 → 20 would NOT slice. Fixed to:
- Re-fetch only when the requested limit is LARGER than what's cached
- Always apply `_tlAllCommits.slice(0, limitN)` before filtering — this makes 100 → 20 work correctly
- Added `onchange="_applyTimelineFilters()"` to the select element so it fires immediately on change

### Fix 3 — Replace "COMPLETED" status with smarter labels

Added `_repoStatusLabel(repo)` helper that returns:
- `FULLY ANALYZED` (green, weight 700) when `analysis_count >= commit_count > 0`
- `INGESTED` (muted) when COMPLETED but not fully analyzed
- `INGESTING` (amber) during ingestion
- `FAILED` (red) on failure

Added CSS classes `.status-full`, `.status-done`, `.status-ingesting`, `.status-failed`. Applied to repo cards and the `#sh-status` header badge.

### Fix 4 — Timeline: add date range calendar filter

Added two `<input type="date">` fields (`#tl-date-from`, `#tl-date-to`) to the timeline filter bar. Integrated into `_applyTimelineFilters()` — date comparison uses ISO string prefix matching. Date inputs use `color-scheme: dark` for proper dark mode rendering.

### Fix 5 — Case Study: stronger style for Key Architectural Pattern

In `_renderSectionCards()`, a regex `/architect|key pattern|design pattern|structural pattern/i` detects architectural pattern headings. Matched cards get:
- Extra class `cs-arch-pattern-card open` (auto-expanded)
- CSS: `border-left: 4px solid var(--accent)`, `background: rgba(99,102,241,0.08)`
- Icon changed to 🏛
- Title styled `font-size: 1rem; font-weight: 700; color: var(--accent)`

### Fix 6 — Case Study: make commit SHAs into links

Added `_linkifyCommitShas(html, canonicalUrl)` that post-processes rendered HTML. Uses a negative lookbehind to avoid double-linking already-linked URLs. Applies to GitHub repos only. Links open in `_blank` with monospace accent styling.

### Fix 7 — Case Study: Key Mistakes section uses better commit search

Replaced the single-keyword approach with `_searchCommitsBySectionBody(bodyText, label)`:
1. Extracts 7–40 char hex strings from section body text
2. Cross-references against loaded commits by SHA prefix
3. If SHA matches found, uses `_filterByEvidenceShas()` for exact filtering
4. Falls back to extracting meaningful technical keywords from body text (not title words)

The search buttons in section cards now carry `data-body` with the full section text.

### Fix 8 — Dark mode: increase contrast and font size

- `--text` changed from `#e2e8f0` to `#eef2f7` (higher luminance, closer to white without halation)
- `--muted` changed from `#94a3b8` to `#9ca3af` (WCAG AA on all dark surfaces)
- `body font-size` increased from `14px` to `15px`
- `body line-height` added: `1.6`
- `td font-size` explicitly set to `14px`
- `th font-size` increased to `12px`, `font-weight` to `700`

### Fix 9 — Remove Deep Analysis → Patterns tab

Removed the "Patterns" `<button class="tab-btn">` and `<div class="tab-panel" id="tab-patterns">` from the Deep Analysis panel. The `loadPatterns()` function is retained because it populates `patternsData` used by `_rebuildPatternsChart()` for the Overview tab. A guard was added so `loadPatterns` returns early if `patterns-content` doesn't exist.

### Fix 10 — Contributors: bigger "Search on GitHub" + fix Top files overflow

- "Search on GitHub ↗" link now styled as a proper button: `font-size: 13px`, `font-weight: 600`, `border: 1px solid var(--accent)`, `border-radius: 4px`
- Top files container gets `flex-wrap: wrap; overflow: hidden; max-width: 100%`
- Each `<code>` tag gets `max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: inline-block; vertical-align: bottom`

### Fix 11 — Hero: bigger, more professional, award-winning design

Hero section:
- `h1` font size changed to `clamp(1.8rem, 4vw, 3rem)` with `font-weight: 800`, `letter-spacing: -0.03em`, `line-height: 1.1`
- Hero gradient text: `linear-gradient(135deg, var(--text) 0%, var(--accent) 100%)` with `-webkit-background-clip: text`
- Radial background glow: `radial-gradient(ellipse at 50% 0%, rgba(99,102,241,0.13) 0%, transparent 70%)`
- Subtitle: `font-size: 1.05rem`

Overall page:
- `repo-card`, `stat-card`, `chart-box` border-radius increased to `12px`
- `box-shadow: 0 1px 3px rgba(0,0,0,0.3)` added to cards and chart boxes
- `.view-nav-btn` and `.tab-btn` font-size increased to `14px` with `letter-spacing: 0.02em`
- `.add-repo-input` font-size increased to `15px`, padding to `0.75rem 1rem`, border-radius to `8px`
- `.hdr-badge` font-size increased to `11px`, font-weight to `700`

## Design Decisions

- Gradient text on hero H1 uses CSS `background-clip: text` — widely supported in modern browsers, graceful degradation to plain text in unsupported environments
- SHA linkification uses a negative lookbehind `(?<!href=["'][^"']{0,200})` to avoid double-linking. The lookbehind length cap (200 chars) prevents catastrophic backtracking
- Architectural pattern card auto-expands (`open` class added) so the content is immediately visible — other sections collapse by default
- `loadPatterns()` is kept because the Overview charts depend on `patternsData`; the Patterns tab UI is what was removed, not the data loading

## Gotchas

- The `_tlAllCommits.slice(0, limitN)` fix needed the condition to be INVERTED from the original: re-fetch when limit is LARGER than cached, not smaller
- Date input `color-scheme: dark` is necessary on Windows/Chrome to render the calendar picker in dark colors matching the UI
- The SHA regex lookbehind can't reference variable-length groups in some JS engines — capped at 200 chars to stay within spec
- `_repoStatusLabel` needs both `commit_count > 0` AND `analysis_count >= commit_count` to show FULLY ANALYZED — a repo with 0 commits should not be shown as fully analyzed

## Test Results

- `ruff check src/ tests/`: All checks passed
- `pytest tests/ -x -q --no-cov`: 546 passed, 8 skipped
