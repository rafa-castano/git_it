## Batch 114 — Sync docs/specs/index.md with real implementation status

### Goal

`docs/specs/index.md` was stale: it stopped at spec 014, missing specs 015-022
entirely, and listed spec 006 (MCP Strategy) as "Draft" when the spec file itself
has said "Implemented" since batch 102. This was a known, flagged gap from a prior
session; today's 16-item program completion (spec 022, the last item) made it the
right time to close it.

### What was checked

Read every spec file's own `Status:` line (`specs/*.md`) before writing anything,
per the evidence-before-interpretation principle — did not assume the index's
existing pattern was correct without checking.

Found: specs 001-004, 007, and 014-020 all say `Status: Accepted` in their own
file, yet the index already listed 001-004/007/014 as "Implemented" — confirming the
index's existing (pre-existing, not introduced here) convention is to track *real,
verified implementation status* (cross-referenced against `docs/progress/` batches),
not to mirror each spec file's own status line verbatim. Individual spec files are not
routinely bumped from "Accepted"/"Draft" to "Implemented" after being built — a
separate, pre-existing documentation-discipline gap, out of scope for this batch.

### What was added

`docs/specs/index.md`:
- `006 | MCP Strategy` — `Draft` → `Implemented` (matches the spec file itself,
  batch 102).
- Added rows for specs 015-022, all `Implemented` — every one of these was verified
  built via its own batch (088-096) and, as of today, live-verified in a running
  browser via the first Playwright QA sweep of the whole 16-item program (batch 113):
  `015` Repo-Specific Case Study Opening, `016` Ask Tab Answer Formatting, `017`
  Activity Chart Zoom Ladder, `018` Commit-Categories Donut Multi-Select, `019`
  GitHub Stars + Language Breakdown, `020` File/Folder Path Linking in Narrative
  Text, `021` Background-Job Fail-Loud, `022` GitHub Discussions Ingestion and
  Narrative Evidence.
- `005` (Documentation Engine) left as `Draft` — no evidence of implementation
  found in `docs/progress/`, so left untouched rather than guessed at.

### Tests added

None — docs-only change, no production code touched.

### Gotchas

- `docs/specs/index.md`'s "status" column is a project-level tracking convention,
  not a mirror of each spec file's own `Status:` header — those two can legitimately
  disagree (the file says "Accepted", the index says "Implemented" once it's
  actually shipped). Worth knowing before "fixing" a future mismatch: check
  `docs/progress/` for real evidence first, don't just copy the spec file's header.
- Did not bump the individual `specs/015-022*.md` files' own `Status:` lines to
  match — that mirrors the existing, repo-wide convention (001-004/007/014-020 all
  have this same header/index mismatch already) rather than introducing a
  one-off fix for only the newest specs.

### Gate

`uv run --group docs mkdocs build --strict` — exit 0, no new warnings.

### Commits

- `docs: sync specs index with real implementation status (spec 006, 015-022)`
