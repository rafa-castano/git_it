# Bug fix — PostgresSynopsisStore migrated from psycopg2 to psycopg v3

## Goal

`PostgresSynopsisStore` (added in batch 68) was written against `psycopg2` (v2) with local
imports, while every other adapter in `postgres.py` uses `psycopg` v3 (the declared project
dependency). This caused `mypy src/` to error with:

```
src/git_it/repository_ingestion/infrastructure/postgres.py:848: error:
  Library stubs not installed for "psycopg2"  [import-untyped]
```

The correct fix is to use the already-installed psycopg v3 API, not to add a `psycopg2` type-stub
package for a dependency that shouldn't be there at all.

## Changes Made

**`src/git_it/repository_ingestion/infrastructure/postgres.py`** (`PostgresSynopsisStore`)
- Replaced `import psycopg2` (local, in each method) with the module-level `psycopg` import
  already present at the top of the file.
- Renamed `__init__` parameter and attribute from `dsn`/`_dsn` to `conninfo`/`_conninfo`
  to match every other Postgres adapter in the file.
- Replaced `conn.cursor()` + `cur.execute()` pattern (psycopg2) with `conn.execute()` directly
  on the connection (psycopg v3).
- `get_synopsis`: replaced `cur.fetchone()` call after a separate `cur.execute()` with a
  single `conn.execute(...).fetchone()` chain.
- `save_synopsis`: removed the `conn.commit()` call inside the cursor block and kept it at the
  connection level (correct psycopg v3 pattern).

## Files Changed

- `src/git_it/repository_ingestion/infrastructure/postgres.py` — `PostgresSynopsisStore` only.

## Tests Added

None — the existing `tests/unit/test_postgres_adapters.py` covers the Postgres adapters; no
behaviour change was introduced. `mypy src/` now reports `Success: no issues found in 40 source
files`.

## Gotchas

- psycopg v3's `Connection.execute()` returns a `Cursor` directly; chaining `.fetchone()` on it
  is idiomatic and saves a separate cursor context manager.
- The `psycopg2`-style `with conn.cursor() as cur:` + `conn.commit()` inside the block is valid
  psycopg2 but not the psycopg v3 pattern — the commit should happen at the connection level.
