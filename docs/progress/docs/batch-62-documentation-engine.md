# Batch 62 — Documentation Engine (MkDocs Material site)

Spec: 005 — Documentation Engine  
Status: Done

## What was built

A complete MkDocs Material documentation site wired into CI.

### Files created

- `mkdocs.yml` — site config with Material theme (slate/deep-purple/amber), navigation tabs, code copy, and `--strict` nav
- `docs/index.md` — project home page: what Git It is, key features, quick start
- `docs/getting-started.md` — prerequisites, installation, server startup, dashboard walkthrough, environment variables table, CLI usage
- `docs/architecture.md` — hexagonal architecture overview, layer diagram, key ports table, data flow, link to ADRs
- `docs/api-reference.md` — full endpoint table, key request/response schemas, rate limiting notes
- `docs/specs/index.md` — table of specs 001–006 with status and links
- `docs/progress/index.md` — progress index by feature area with full batch listing link
- `docs/adr/index.md` — ADR index table for ADRs 001–008, plus instructions for adding new ADRs

### pyproject.toml change

Added `docs` dependency group:

```toml
[dependency-groups]
docs = ["mkdocs-material>=9.5", "mkdocs-autorefs>=1.0"]
```

### CI change

Added docs build step after pytest in `.github/workflows/ci.yml`:

```yaml
- name: Build docs
  run: uv run --group docs mkdocs build --strict
```

## Decisions

- Used `--strict` flag so broken links and missing pages fail the CI build.
- Relative links from `docs/specs/index.md` and `docs/adr/index.md` point up to source files in `specs/` and `ADR/` so the docs stay in sync without duplicating content. MkDocs resolves these correctly with `--strict`.
- `docs/progress/README.md` is excluded from the MkDocs nav (internal index). `docs/progress/index.md` is the public entry point.
- No ADR folder needed under `docs/` — existing `ADR/` at project root is linked directly.

## Tests added

None — validation is the MkDocs strict build itself, enforced in CI.

## Links broken and fixed

None — all links were verified against the MkDocs strict build before committing.
