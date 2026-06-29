# Batch 65 — UI interactive fixes: chart cross-linking, timeline filter, commit file filter, and `files_changed` API field

## Goal

Fix five interactive bugs in the dashboard where clicking chart elements either navigated to the wrong view, showed the wrong data, or left stale filter state. Also surface `files_changed` per commit through all backend layers so the commit file filter has real data to match against.

## Changes Made

### Fix 1 — `files_changed` field across all backend layers

Commits now expose the list of files they touched, flowing from SQLite through the port, schema, and route.

**`src/git_it/repository_ingestion/application/ports.py`**
- Added `files_changed: tuple[str, ...] = ()` to `CommitWithAnalysisRecord`

**`src/git_it/repository_ingestion/infrastructure/sqlite.py`** (`SqliteCommitWithAnalysisReader`)
- Added `LEFT JOIN file_facts ff ON ff.commit_sha = ca.commit_sha AND ff.repository_id = ca.repository_id`
- Added `GROUP_CONCAT(ff.file_path, '|||') AS files` to the SELECT
- Added `GROUP BY` clause so the join doesn't duplicate rows
- Parses the concatenated string: `tuple(str(row[4]).split('|||')) if row[4] else ()`

**`src/git_it/api/schemas.py`**
- Added `files_changed: list[str] = []` to `CommitSummaryItem`

**`src/git_it/api/routes/repos.py`** (`get_commits`)
- Added `files_changed=list(record.files_changed)` when constructing `CommitSummaryItem`

### Fix 2 — Repo card signal tags: missing tooltips

The `.dna-pill` CSS class sets `cursor: help` but the signal spans in `_renderRepoCard` had no `data-tip` attribute, so hovering showed only the question-mark cursor with no text.

Added `data-tip` to each of the four signal spans, pointing to existing tip keys:

| Signal | `data-tip` key |
|--------|---------------|
| ⚡ Refactor Wave | `sigRefactor` |
| ↩️ Reverts | `sigRevert` |
| 🧪 Test Growth | `sigTest` |
| 🔥 N hotspots | `tlHotspot` |

The global `mouseover` tooltip engine picks these up automatically — no new tip keys needed.

### Fix 3 — Timeline "All (10)" bug: stale limit selector

**Root cause:** `loadTimeline` read its fetch limit from `tl-limit-select`. After visiting a repo, the select was rebuilt to e.g. `10 commits`. On the next repo open, `loadTimeline` read `10`, fetched 10 commits, and rebuilt the select to "All (10)" — hiding the remaining analyzed commits.

**Fix:** `loadTimeline` now always fetches with `limit=1000`, ignoring the select entirely. The select becomes a pure display control (client-side slicing via `_applyTimelineFilters`). The `_applyTimelineFilters` re-fetch condition was simplified: `if (limitN > _tlAllCommits.length)`.

Also removed the redundant **Apply** button from the timeline filter bar — all inputs already fired `onchange="_applyTimelineFilters()"` so the button was dead.

### Fix 4 — TOP HOTSPOT FILES chart click: keyword filter replaced with SHA filter

**Root cause:** Clicking a bar called `_searchCommitsByFile(filePath)`, which:
1. Extracted just the basename (`filePath.split('/').pop()`)
2. Set `keyword-filter` to that string
3. Relied on `files_changed` being populated and on the basename matching

`files_changed` was empty for all commits (fix 1 addresses the data gap), and keyword matching was unreliable for partial path names. Additionally, `allCommits` only held 20 commits (`commitsLimit = 20`), so most analyzed commits were invisible to the filter.

**Fix (chart `onClick`):** Now uses `_filterByEvidenceShas(h.evidence_commit_shas, 'File: fname')` when the hotspot has evidence SHAs. Falls back to `_searchCommitsByFile` only when SHAs are unavailable. This is consistent with how the Patterns tab's hotspot buttons already work.

**Fix (`_filterByEvidenceShas`):** Made async. Before applying the SHA filter, bumps `commitsLimit` to `1000` and reloads `allCommits` so no evidence SHA is silently missing from the in-memory set.

### Fix 5 — COMMIT ACTIVITY chart click: date filter instead of scroll

**Root cause:** Clicking an activity bar called `switchView('timeline')` then tried to find a DOM element `tl-month-YYYYMM` to scroll to. That element doesn't exist, so nothing happened — all commits were shown.

**Fix:** Computes `fromDate` / `toDate` from the label format returned by `buildActivityData`:

| Granularity | Label example | fromDate | toDate |
|-------------|---------------|----------|--------|
| month | `"2024-03"` | `2024-03-01` | `2024-03-31` (last day via `new Date(y, m, 0)`) |
| day | `"2024-03-15"` | `2024-03-15` | `2024-03-15` |
| hour | `"2024-03-15 14h"` | `2024-03-15` | `2024-03-15` |

Sets `tl-date-from` and `tl-date-to` inputs, then calls `_applyTimelineFilters()` — which already had date-range filtering logic from Batch 64 Fix 4.

### Fix 6 — Commits tab: stale filter when clicking the tab directly

**Root cause:** Navigating to Commits via a chart (donut, hotspot) correctly applied a filter and showed the `commits-back-bar`. But clicking the Commits tab a second time called `switchTab('commits')` without clearing the filter, so the filtered view persisted.

**Fix:** The tab button `click` listener now calls `_clearCommitFilters()` before `switchTab` when the target tab is `commits`. Programmatic calls to `switchTab('commits')` from chart handlers are unaffected — they bypass the button listener.

```js
document.querySelectorAll('.tab-btn').forEach(btn =>
  btn.addEventListener('click', () => {
    if (btn.dataset.tab === 'commits') _clearCommitFilters();
    switchTab(btn.dataset.tab);
  })
);
```

## Files Changed

- `src/git_it/static/index.html` — fixes 2–6
- `src/git_it/repository_ingestion/application/ports.py` — fix 1
- `src/git_it/repository_ingestion/infrastructure/sqlite.py` — fix 1
- `src/git_it/api/schemas.py` — fix 1
- `src/git_it/api/routes/repos.py` — fix 1

## Gotchas

- `loadTimeline` now always fetches `limit=1000`. For repos with >1000 analyzed commits the excess is silently dropped — acceptable for an academic project scope.
- `_filterByEvidenceShas` is now `async`. Callers that don't `await` it (chart `onClick`) are fine — the filter applies after the reload; the UI updates visually once the promise resolves.
- Month last-day computation uses `new Date(y, m, 0)` where `m` comes from the `"YYYY-MM"` string as a 1-indexed number. `new Date(2024, 3, 0)` correctly returns March 31 because month 3 (April) day 0 = March 31.
- The Apply button removal (fix 3) is safe — every filter input already had `onchange="_applyTimelineFilters()"` wired.

## Tests

No new unit tests. All fixes are frontend interaction logic; correctness is verifiable by manual browser interaction.
