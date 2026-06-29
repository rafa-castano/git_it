# Batch 76 — Extract CSS and JS from index.html to static files

## Goal

Split the monolithic `src/git_it/static/index.html` (~2309 lines) into three files:
- `index.html` — markup only (~175 lines)
- `app.css` — all styles (356 lines)
- `app.js` — all JavaScript (1805 lines)

Simultaneously extract a reusable `pollUntilDone()` utility from three copies of a similar polling loop.

## Changes Made

### File extraction

- Stripped the `<style>…</style>` block from `index.html` (lines 10–367 original). Wrote its content to `app.css`, removing the 4-space HTML indentation.
- Stripped the `<script>…</script>` block from `index.html` (lines 530–2307 original). Wrote its content to `app.js`.
- Replaced the `<style>` block with `<link rel="stylesheet" href="/static/app.css">` (FastAPI mounts static at `/static`).
- Replaced the `<script>` block with `<script src="/static/app.js"></script>`.

### Polling utility (`pollUntilDone`)

Added at the top of `app.js`:

```javascript
function pollUntilDone({ url, interval, onTick, onDone, onError }) {
  const intervalId = setInterval(async () => {
    try {
      const data = await apiFetch(url);
      const done = await onTick(data);
      if (done) {
        clearInterval(intervalId);
        if (onDone) await onDone();
      }
    } catch (err) {
      clearInterval(intervalId);
      if (onError) onError(err);
    }
  }, interval);
  return intervalId;
}
```

Replaced three polling call sites:

| Function | Interval | Stop condition |
|---|---|---|
| `_pollForRepo` | 3000 ms | Repo found in `/api/repos` list |
| `_pollRegenStatus` | 2000 ms | `!s.running` from regen-status endpoint |
| `_pollAnalyzeStatus` | 2000 ms | `!s.running` from analyze/status endpoint |

`_pollForRepo` is the most complex: it stores the interval ID in `_ingestPoll` (external variable) so a new ingest can cancel a previous one. The refactored version stores the return value of `pollUntilDone` in `_ingestPoll` — same behavior.

`_pollAnalyzeStatus` has per-tick UI updates (button text while running). These stay in `onTick`; the completion logic moves to `onDone`. Added a `if (!btn) return;` guard in `onDone` to match the original `if (!btn) { clearInterval; return; }` early-exit path.

### Test updates (`tests/unit/test_api_static.py`)

Three tests were checking index.html for strings that are now in `app.js`:

- `test_static_index_contains_api_calls` — now checks that index.html references `app.js` AND that `app.js` contains `/api/repos`.
- `test_static_index_has_four_tabs` — "Patterns" was removed as a UI tab in batch 65; it only appeared in the inline JS. Updated to check for the actual four tabs: Overview, Case Study, Commits, Contributors.
- `test_static_index_has_tooltip_system` — "TIPS" constant is in `app.js`; `global-tip` element and `data-tip` attributes remain in `index.html`. Test now checks each in the right file.

## Files Changed

- `src/git_it/static/index.html` — 2309 lines → 175 lines (markup only)
- `src/git_it/static/app.css` — new file, 356 lines
- `src/git_it/static/app.js` — new file, 1805 lines (includes `pollUntilDone` utility)
- `tests/unit/test_api_static.py` — updated 3 tests to reflect external JS/CSS

## Gotchas

- The CSS in index.html was indented by 4 spaces (HTML indentation). Stripping exactly 4 leading spaces per line produces clean CSS. A naïve `"\n".join(lines)` approach doubled newlines because each line already ended with `\n`.
- `pollUntilDone` returns the interval ID. `_pollForRepo` assigns this to `_ingestPoll` synchronously, so any async callback that sets `_ingestPoll = null` does so safely — the assignment completes before the first tick fires.
- The FastAPI static mount is at `/static`, so external files must use `/static/app.css` and `/static/app.js`.
