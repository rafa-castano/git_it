## Batch 51 — GitHub username extraction and analyze progress indicator

### Goal

Two small API/UI features: surface the contributor's GitHub username when the email is a GitHub noreply address, and show a live percentage in the "Running…" analyze button.

### What was added

**GitHub username extraction:**
- Added `author_email: str = ""` field to `ExtractedCommit` dataclass
- `GitPythonCommitExtractor` now copies `commit.author.email` into the field
- `ContributorItem` schema gained `github_username: str | None = None`
- Contributors endpoint derives the username from both GitHub noreply formats:
  - old: `alice@users.noreply.github.com` → `alice`
  - new: `12345678+alice@users.noreply.github.com` → `alice`
- Dashboard links directly to `https://github.com/{username}` when available; falls back to a search URL

**Analyze progress:**
- Added `AnalyzeStatusResponse(running, done, total, pct)` schema
- Added thread-safe `_analyze_progress` dict keyed by `repository_id` in the route module
- `analyze_commits()` accepts an `on_progress: Callable[[int, int], None]` callback
- Background thread updates the progress dict after every commit (cached, skipped, or analyzed)
- New `GET /api/repos/{id}/analyze/status` endpoint serves the progress
- Dashboard polls every 2 seconds during analysis; button shows "Running 25%"

### Tests added

See batch 54 — TDD endpoint tests were written as a catch-up after these features.

### Gotchas

- GitHub noreply emails come in two distinct formats (old and new); both must be handled
- `on_progress` is called for every commit including cached and skipped ones so the percentage always reaches 100

### Commits

- `feat: extract GitHub username from contributor emails and add analyze progress tracking`
