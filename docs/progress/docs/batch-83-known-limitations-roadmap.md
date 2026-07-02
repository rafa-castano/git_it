# Batch 83 — Known Limitations, Roadmap, and stale doc-index correction

Status: Done

## Goal

Give the MkDocs site an honest "Known Limitations" and "Roadmap" view, and fix
doc-site index pages that had drifted from their source files.

## What was added

- `docs/architecture.md` — new **Known limitations** section summarizing ADR
  010's three accepted limitations (in-memory progress state and permissive
  CORS still open; direct SQLite reader instantiation resolved 2026-07-02 by
  spec 014), and a new **Roadmap** section listing open Draft specs (005, 006,
  008) with their current gap, not invented timelines.
- `docs/getting-started.md` — added the missing `DATABASE_URL` row to the
  Environment Variables table, plus a note on the fail-loud Postgres contract
  from spec 014 (no silent SQLite fallback).

## Stale docs fixed (evidence-grounded, found while doing the above)

- `docs/adr/index.md` listed ADRs 001–008 as "Proposed" — every `ADR/*.md`
  source file actually reads `Status: Accepted`. Corrected all eight rows.
- `docs/specs/index.md` listed spec 008 (Repository Deletion) as
  "Implemented" — its source header reads `**Status:** Draft`, and
  `tests/integration/test_repo_lifecycle.py` has no delete coverage. Corrected
  to "Draft (built, untested at integration level)" — the feature (DELETE
  endpoint + delete UI) is functionally built, just never bumped past Draft
  and not integration-tested.
- `docs/specs/index.md` was missing spec 014 entirely; added as "Implemented".

## Gotcha caught by the CI docs gate

The first draft of `docs/architecture.md` linked out-of-tree source files
with real Markdown links (`[spec 014](../specs/014-postgres-read-layer.md)`).
`mkdocs.yml` sets `docs_dir: docs`, so MkDocs's strict link checker cannot
resolve links that point outside that tree — `mkdocs build --strict` failed
with 5 "target is not found" warnings. `docs/specs/index.md` and
`docs/adr/index.md` already establish the working convention: cite `specs/`
and `ADR/` paths as plain backtick text, not as Markdown links. Rewrote the
five offending links to match. Verified with a clean
`uv run --group docs mkdocs build --strict` afterward.

## Tests added

None — docs-only change (CODEX.md: TDD does not apply to trivial
documentation-only changes). Validation is `mkdocs build --strict`, run
locally and gated in CI (`.github/workflows/ci.yml`).

## Files changed

- `docs/adr/index.md`
- `docs/specs/index.md`
- `docs/architecture.md`
- `docs/getting-started.md`

## Commits

- e3c6a45 — docs: add Known Limitations and Roadmap, fix stale ADR/spec status indexes
