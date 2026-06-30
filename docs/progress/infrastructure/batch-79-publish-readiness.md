# Batch 79 — Publish readiness: paths, hygiene, docs

## Goal

Prepare the repository for public GitHub publication by removing machine-specific absolute
paths, cleaning up stray untracked artifacts, and updating stale documentation indices.

## Changes

### `.mcp.json` (machine-specific paths)

- Added `.mcp.json` to `.gitignore` — the file contained absolute Windows paths that would
  break for any other cloner.
- Created `.mcp.json.example` (committed) with portable values: repo path `"."` and
  `"${HOME}/.claude/skills"` for the global skills directory. Users copy and adapt it locally.
- Removed `.mcp.json` from git tracking (`git rm --cached`); the local copy is preserved.

### Stray root artifacts

- Added `site/` (MkDocs generated output), `*.stackdump`, and `/*.png` to `.gitignore`.
- Moved 11 batch-evidence screenshots from the repo root to `docs/assets/`.
- Removed `bash.exe.stackdump`.

### Documentation indices

- `docs/specs/index.md`: added specs 007 (Cost Estimation) and 008 (Repository Deletion),
  both already implemented in prior batches but missing from the index.
- `docs/adr/index.md`: added ADR 009 (Analyze Commits Oldest-First, Accepted) and ADR 010
  (Accepted Limitations of the Local-First Single-Process MVP, Accepted), both already filed
  as `ADR/*.md` but missing from the index.

## Tests

No application logic changed; no tests required.

## Files changed

- `.gitignore` — four new ignore rules
- `.mcp.json.example` — new file (committed)
- `docs/assets/` — 11 screenshots relocated here
- `docs/progress/infrastructure/batch-79-publish-readiness.md` — this file
- `docs/specs/index.md` — specs 007/008 added
- `docs/adr/index.md` — ADR 009/010 added
