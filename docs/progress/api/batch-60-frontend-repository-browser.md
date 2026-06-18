# Batch 60 — Frontend repository browser (home view)

## Goal

Add a proper home/landing view so users can discover, ingest, and navigate to
repositories from the UI, without needing to know an internal `repository_id`.

## What was added

### Hero section
A two-line description of Git It's purpose is now displayed above the URL input
on every fresh load, providing first-time context with a clear `<h1>` heading.

### URL input improvements
- Placeholder text updated to `https://github.com/owner/repo or owner/repo`
- `aria-label="GitHub repository URL"` on the `<input>` (was vague before)
- `aria-describedby="ingest-hint"` links input to hint text
- Button label changed from `+ Add` to `Analyze` with a search icon SVG

### Ingest loading state (aria-busy)
- `aria-busy="true"` is set on the Analyze button while a request is in flight
- An inline CSS spinner appears inside `#ingest-status` during ingestion polling
- Button is `disabled` during the in-flight window to prevent double-submit
- Both `aria-busy` and `disabled` are cleared on success or error

### Repo cards grid — ARIA
- Grid `<div>` now has `role="list"` and `aria-label="Analyzed repositories"`
- Each card has `role="listitem"` (was `role="button"`, conflicting with list)
- Card `aria-label` includes commit count, analysis count, and status
- Status badge gets `aria-label="Status: {value}"`

### GitHub icon link on cards
- Each card now shows a subtle GitHub octicon link that opens the repo's
  canonical URL in a new tab, accessible with `aria-label="View {name} on GitHub"`
- Click is stopped from propagating so it does not also open the dashboard

### Empty state
- Empty state text updated to match the brief: "No repositories analyzed yet.
  Paste a GitHub URL above to get started."
- Wrapper gets `role="status"` so screen readers announce it on load

### Back button
- Sidebar back button `aria-label` updated to "Back to home"

## Gotchas

- The existing home view in `index.html` already implemented the two-view router,
  repo cards grid, ingest flow, and polling — this batch refines and extends it
  rather than rewriting it.
- The `rc-open-btn` inside cards keeps `aria-hidden="true"` / `tabindex="-1"`
  because the card itself carries the interaction — inner button is visual only.
- GitHub link uses `event.stopPropagation()` to prevent the card click handler
  from also triggering `selectRepo`.

## Commits

- `feat: add home view with URL input and repository browser`
