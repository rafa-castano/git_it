## Batch 105 — Fix latent PostgreSQL migrations-path off-by-one

### Goal

Fix a pre-existing bug in `initialize()` (the PostgreSQL schema bootstrap) that
made it resolve `migrations/001_initial.sql` to a path **above** the repository
root — so any run against a real PostgreSQL backend would raise
`FileNotFoundError` before a single migration executed.

The bug was surfaced (not caused) by batch 104's package split. The original
`infrastructure/postgres.py` used `Path(__file__).parents[5]`, but `parents[4]`
is already the repository root — so `parents[5]` pointed one level too high. When
batch 104 moved the code one directory deeper into
`infrastructure/postgres/_common.py`, the index was bumped `parents[5] → parents[6]`
to faithfully preserve the *old resolved target* (correct for a behavior-preserving
refactor) — which preserved the off-by-one. This batch corrects it to the value
that actually resolves to the repo-root `migrations/` directory.

### Why it was invisible

The only tests that call `initialize()` live in `tests/unit/test_postgres_adapters.py`,
which is `pytest.mark.skipif` unless `DATABASE_URL` starts with `postgresql`. Locally
(SQLite) that whole module is skipped, so `initialize()` was never exercised and the
broken path never triggered. But `composition.py` calls `postgres_initialize(conninfo)`
on every Postgres store build — so the bug bites any real Postgres deployment (and CI
runs that stand up a Postgres service).

### What was added

**`src/git_it/repository_ingestion/infrastructure/postgres/_common.py`**
- Extracted the path resolution into a testable seam `_migrations_path() -> Path`,
  and had `initialize()` call it.
- Corrected the index `parents[6] → parents[5]` (from `_common.py`, `parents[5]` is
  the repository root that contains `migrations/`). Verified empirically:
  `parents[5]` → `git_it/migrations/001_initial.sql` (`exists=True`); `parents[6]` →
  `TFM/migrations/...` (`exists=False`).

### Tests added

**`tests/unit/test_postgres_migrations_path.py`** (new, 2 tests, run unconditionally —
no PostgreSQL needed, exercising only filesystem resolution):
- `test_migrations_path_resolves_to_existing_file` — asserts `_migrations_path().is_file()`
  (RED against `parents[6]`, GREEN after the fix).
- `test_migrations_path_points_at_the_initial_migration` — asserts the resolved
  path is `.../migrations/001_initial.sql`.

Full suite: **813 passed, 18 skipped** (was 811 before this batch; +2).

### Gotchas

- `Path(__file__).parents[N]` is **repo-relative**, invariant across checkouts —
  so this was broken everywhere (local, CI, prod), not a machine-specific artifact.
  The deep OneDrive nesting on the dev machine is irrelevant to the index math.
- The regression test deliberately does NOT connect to PostgreSQL — it guards only
  the path resolution, which is the part that was wrong and the part the skipped
  adapter tests never covered without a live DB. This is what makes it a *local*
  guard against future file moves.
- Batch 104 (the split) remains a correct, behavior-preserving refactor: it
  preserved the old (broken) target exactly. This batch is the separate, TDD'd
  correctness fix — kept as its own commit rather than folded into the refactor.

### Commits

- `fix: resolve PostgreSQL migrations path to the repository root`
