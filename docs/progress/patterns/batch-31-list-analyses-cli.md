## Batch 31 — list-analyses CLI command

### Goal

Add a read-only `list-analyses` subcommand so users can inspect stored commit analyses without triggering any LLM calls.

### Source of truth

- MVP usability: inspect cache before running `case-study`

### Examples covered

- `list-analyses <url>` exits 0, reuses `_print_commit_analyses` output format
- Empty store shows "No analyses" message
- `--limit N` passed through to `list_analyses(repository_id, limit=N)`

### Tests added

- `tests/unit/test_list_analyses_cli.py` — 4 tests

### Production behavior added

- `interfaces/cli.py` — `AnalysisStoreReader`, `ListAnalysesFactory` protocols; `list-analyses <url> [--limit N]` subcommand; `_run_list_analyses`; `_default_list_analyses_factory` wires `SqliteCommitAnalysisStore`
