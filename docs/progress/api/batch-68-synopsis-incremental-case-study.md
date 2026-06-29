# Batch 68 — Synopsis-based incremental case study context

## Goal

Reduce the token cost of incremental case study updates by storing a compact, audience-neutral
synopsis (~150–250 words) after each generation. The incremental path then uses this synopsis as
LLM context instead of replaying the full narrative, while falling back gracefully when no synopsis
exists yet.

Commit: `bf15ab45494741cf9b8120bc3ad157c06cbd1ceb`

## Changes Made

### `_extract_synopsis()` — strip synopsis from stored narrative

`src/git_it/repository_ingestion/application/narrative_service.py`

New private function `_extract_synopsis(raw_output: str) -> tuple[str, str | None]`. Searches for
the last `\n## Synopsis` marker in the LLM output using `rfind`. Returns the narrative (text before
the marker, right-stripped) and the synopsis (text after the marker, stripped). Returns
`(raw_output, None)` when the marker is absent or the section is blank. Both the full and
incremental generation paths call this function on the LLM response before storing the narrative.

### LLM prompt instruction for the Synopsis section

`_SYNOPSIS_INSTRUCTION` constant added to `narrative_service.py`:

> "After all sections, add a `## Synopsis` section: a compact internal summary (150–250 words)
> covering key patterns, architectural decisions, and engineering insights extracted from this case
> study. Write it in plain prose, audience-neutral. This section is used internally to seed future
> updates and is NOT displayed to users."

Both `_BASE_PROMPT` and `_BASE_INCREMENTAL_PROMPT` templates now include
`{synopsis_instruction}` at the end.

### `SynopsisStore` protocol

`src/git_it/repository_ingestion/application/ports.py`

New `SynopsisStore` protocol with two methods:
- `save_synopsis(repository_id: str, synopsis: str) -> None`
- `get_synopsis(repository_id: str) -> str | None`

### `SqliteSynopsisStore`

`src/git_it/repository_ingestion/infrastructure/sqlite.py`

`SqliteSynopsisStore` with `initialize()`, `save_synopsis()`, and `get_synopsis()`. The
`initialize()` method creates the `repository_synopsis` table (one row per repository, upserted on
`repository_id`). Both save and get use `sqlite3.connect` in context-manager form.

### `PostgresSynopsisStore`

`src/git_it/repository_ingestion/infrastructure/postgres.py`

`PostgresSynopsisStore` mirrors the SQLite implementation using `psycopg2`. The upsert uses
`ON CONFLICT (repository_id) DO UPDATE SET synopsis = EXCLUDED.synopsis, updated_at = EXCLUDED.updated_at`.

### `repository_synopsis` table

Added to two places:

- **SQLite auto-init**: `SqliteSynopsisStore.initialize()` runs `CREATE TABLE IF NOT EXISTS
  repository_synopsis (repository_id TEXT PRIMARY KEY, synopsis TEXT NOT NULL, updated_at TEXT NOT NULL)`.
- **Postgres migration**: `migrations/001_initial.sql` now contains `CREATE TABLE IF NOT EXISTS
  repository_synopsis (repository_id TEXT PRIMARY KEY, synopsis TEXT NOT NULL, updated_at
  TIMESTAMPTZ NOT NULL DEFAULT NOW())`.

### `NarrativeService` integration

`NarrativeService.__init__` accepts `synopsis_store: SynopsisStore | None = None` (optional,
defaults to `None` for backward compatibility).

**Full generation path** (`_generate_full`): calls `_extract_synopsis` on the raw LLM response;
saves the synopsis via `synopsis_store.save_synopsis` when both a synopsis was extracted and a
store is wired.

**Incremental generation path** (`_generate_incremental`): reads `synopsis_store.get_synopsis`
before constructing the user message. When a synopsis is available, `prior_context` is set to the
synopsis and the user message section header changes to `## Prior Summary`; when not available,
the full `existing.narrative` is used (header remains `## Existing Case Study`). After the LLM
call, the new synopsis is extracted and saved the same way as in full generation.

### Composition wiring

`src/git_it/repository_ingestion/composition.py`

Both the SQLite and Postgres branches of `build_narrative_service` now construct and pass a
synopsis store:
- SQLite: `SqliteSynopsisStore(db_path)` with `.initialize()` called before use.
- Postgres: `PostgresSynopsisStore(conninfo)` wired alongside `PostgresCaseStudyStore`.

## Files Changed

- `migrations/001_initial.sql` — `repository_synopsis` table for Postgres
- `src/git_it/repository_ingestion/application/ports.py` — `SynopsisStore` protocol
- `src/git_it/repository_ingestion/application/narrative_service.py` — `_extract_synopsis`,
  `_SYNOPSIS_INSTRUCTION`, synopsis extraction in full + incremental paths, `synopsis_store` param
- `src/git_it/repository_ingestion/infrastructure/sqlite.py` — `SqliteSynopsisStore`
- `src/git_it/repository_ingestion/infrastructure/postgres.py` — `PostgresSynopsisStore`
- `src/git_it/repository_ingestion/composition.py` — wiring for both backends
- `tests/unit/test_synopsis_extraction.py` — new (4 tests)
- `tests/unit/test_synopsis_service.py` — new (6 tests)
- `tests/unit/test_synopsis_store_sqlite.py` — new (5 tests)

## Tests Added

15 new unit tests across three new files:

**`test_synopsis_extraction.py`** (4 tests): no-synopsis passthrough, clean strip of synopsis
section, empty synopsis returns `None`, `rfind` uses the last marker when multiple `## Synopsis`
markers appear.

**`test_synopsis_service.py`** (6 tests): synopsis stripped from stored narrative; synopsis saved
to store; missing synopsis in LLM output does not break flow; incremental uses synopsis as `##
Prior Summary` instead of full narrative; incremental falls back to full narrative when no synopsis
stored; `force=True` overwrites existing synopsis.

**`test_synopsis_store_sqlite.py`** (5 tests): `get_synopsis` returns `None` for unknown repo;
roundtrip save/get; upsert overwrites old synopsis; different repos are independent; `initialize`
is idempotent.

## Gotchas

- `_extract_synopsis` uses `rfind` (last occurrence) deliberately: if the LLM mistakenly inserts
  an `## Synopsis` header mid-narrative, only the final one is treated as the synopsis section.
- The synopsis is audience-neutral by design. A single synopsis stored per repository serves all
  audience variants (beginner, expert).
- When `synopsis_store is None` (e.g. in tests that do not wire it), the service silently skips
  both storing and reading — no change in behaviour for callers that do not opt in.
- The incremental prompt's section header changes from `## Existing Case Study` to
  `## Prior Summary` when a synopsis is used, so the LLM can distinguish between the two context
  types in its reasoning.
