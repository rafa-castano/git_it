## Batch 136 — Unify all documentation under `docs/` (move ADR/ and specs/ into the tree)

### Goal

Consolidate the project's documentation so everything lives under `docs/`: move the
root-level `ADR/` (17 files) and `specs/` (27 files) directories into `docs/adr/` and
`docs/specs/` (which already held only their `index.md`), leaving `README.md` as the sole
Markdown file at the repository root. Review and adapt every dependency/reference to the old
paths.

### Investigation before moving anything (evidence first)

- **No runtime code reads these paths.** Grepped all `*.py`/`*.js`: the only matches were two
  test-file docstrings (`test_api_delete.py`, `test_github_repo_metadata_fetcher.py`) and one
  `app.js` comment — all inert prose, never a path opened at runtime. So the move carries zero
  functional/runtime risk.
- **No real Markdown links to the moved files.** Every cross-reference to a spec/ADR across the
  repo is backtick *text*, not a `[...](...)` link (the pre-existing batch-114 convention,
  precisely to keep `mkdocs --strict` green). The one apparent `[spec 014](../specs/...)` match
  is itself inside a backtick code span illustrating that convention, not a live link. So
  moving 44 files into the mkdocs tree could not break link validation.
- **No Dockerfile/CI/pyproject references.** Confirmed the build pipeline never names these
  paths.
- **`.claude/skills/sdd-*` reference `openspec/`, not git_it's `specs/`** — generic gentle-ai
  templates, out of scope.

### What changed

**Moves (44 `git mv`, tracked as renames):**
- `ADR/*.md` → `docs/adr/*.md` (lowercase, matching the existing `docs/adr/index.md` and the
  mkdocs nav's `adr/index.md`).
- `specs/*.md` → `docs/specs/*.md` (matching the existing `docs/specs/index.md`).
- The now-empty root `ADR/` and `specs/` directories were removed.

**Reference adaptation (policy: update pointers, preserve historical narrative):**
- **Path *pointers* to spec/ADR files** (e.g. `` `specs/008-repository-deletion.md` ``) were
  rewritten to `` `docs/specs/008-...` `` / `` `docs/adr/016-...` `` everywhere they appear —
  in the live docs, the two index files, README/CODEX, the moved files' own internal
  cross-references, and the three code comments — via a digit-anchored replacement
  (`specs/[0-9]` → `docs/specs/[0-9]`, `ADR/[0-9]` → `docs/adr/[0-9]`). The digit anchor is what
  makes this safe: it never matches `specs/index.md` (no digit) and never double-prefixes an
  already-correct `docs/specs/…` path (verified: zero pre-existing `docs/specs/0NN` refs). 128
  pointers updated, 0 residual broken pointers remaining anywhere in the repo.
- **Structural location claims** (no filename, so the digit-anchor didn't catch them) were
  updated by hand: both `index.md` files ("source files live in `ADR/`/`specs/` at the project
  root" → "live in this directory (`docs/adr/`/`docs/specs/`)"), the `ADR/NNN-short-title`
  template placeholder, `docs/documentation-standards.md` ("Specs under `specs/`. ADRs under
  `ADR/`."), and `CODEX.md` ("Read the relevant spec under `specs/`").
- **`.dockerignore`**: removed the now-redundant standalone `specs/` line — it is already
  covered by the `docs/` exclusion, and `ADR/` was already covered by `*.md`.

**Deliberately left unchanged — historical narrative in progress docs:** roughly a dozen bare
`` `specs/` `` / `` `ADR/` `` mentions in older `docs/progress/batch-*.md` files that describe
the *past* structure as the reasoning of their time (e.g. batch-115's "specs/ files live at
the repo root, outside the mkdocs tree" was the literal justification for why that batch's gate
only touched `index.md`). These are historical records, not live pointers; rewriting them would
falsify the account of what was true when they were written. Pointers-to-files in those same
docs *were* updated (so they still resolve); only the structural-narrative prose was preserved.

### Verification

- `mkdocs build --strict` → **exit 0**. The 44 newly-in-tree pages surface only as an *INFO*
  "not included in nav" note (not a warning) — the same status other long-standing docs
  (`development-workflow.md`, `testing-strategy.md`, …) already have, so strict tolerates it.
  The nav still points at the `Specs`/`ADRs` index tables; the individual pages build and are
  URL-reachable.
- `ruff check .` / `ruff format --check .` / `mypy src/` → all clean.
- `pytest -q` → **992 passed, 27 skipped** (unaffected — the only code touched was three inert
  comments).
- `node --check src/git_it/static/app.js` → OK.
- Residual-pointer scan across `docs/ src/ tests/ README.md CODEX.md AGENTS.md evals/` → **zero**
  broken `specs/NNN`/`ADR/NNN` references remaining.

### Gotchas

- **`sed -i` on Git Bash rewrote every targeted file's line endings**, so ~22 docs that had no
  path pointer to update still showed as modified (pure EOL/no content diff). These were
  restored (`git checkout`) so the commit contains only the 44 moves plus genuine content
  edits (112 files, +135/−136) — no spurious EOL-only churn. `AGENTS.md` was similarly restored
  (it had no matching reference at all).
- **Windows case-insensitivity trap avoided**: the target is lowercase `docs/adr/` (not
  `docs/ADR/`) to match the existing `index.md` and mkdocs nav. Moving files *into* the
  already-tracked lowercase dir (rather than `git mv ADR docs/ADR` as a whole dir) sidestepped
  the `ADR`-vs-`adr` collision that a whole-directory move would have hit on a case-insensitive
  filesystem.
- **Nav was intentionally not expanded** to list all 44 files individually — the repo's
  existing convention already leaves many docs out of nav (they build as standalone pages
  reachable by URL), and the `index.md` tables remain the entry point. Building out a full
  44-entry ADR/spec nav tree was out of scope for a "unify + fix references" task.

### Commits

- `docs: unify documentation under docs/ — move ADR and specs into the tree, adapt references`
