# Batch 95 — Persistence backend seam for CLI and MCP tools

## Goal

Remove the remaining SQLite-specific assumptions from read-side adapters exposed by the
CLI and MCP/chat tools, so both SQLite and PostgreSQL go through the same persistence
composition seam.

## Changes

### CLI `list-analyses`

- Added `build_commit_analysis_reader(project_root=...)` to the repository ingestion
  composition root.
- Updated `git-it list-analyses` to request its reader from composition instead of
  constructing `SqliteCommitAnalysisStore` directly.

### MCP/chat tool registry

- Replaced direct SQLite imports in `src/git_it/tools/registry.py` with backend-aware
  builders from `src/git_it/repository_ingestion/composition.py`.
- Replaced the SQLite file-exists guard with `database_is_provisioned(project_root=...)`,
  so PostgreSQL-only installations are not treated as empty merely because no local
  SQLite file exists.
- Kept fail-loud behaviour for configured PostgreSQL failures instead of silently
  falling back to SQLite.

### Architecture documentation

- Updated `docs/architecture.md` to make the composition root the explicit persistence
  seam for CLI, API, MCP, and chat adapters.
- Documented that concrete SQLite/PostgreSQL imports belong in infrastructure adapters,
  composition wiring, or adapter-specific tests — not in driving adapters.

## Tests

- `uv run pytest tests/unit/test_list_analyses_cli.py -q`
- `uv run pytest tests/unit/test_tools_registry.py -q`
- `uv run pytest tests/unit/test_tools_registry.py tests/unit/test_mcp_tools.py tests/unit/test_chat_service.py -q`
- `uv run ruff check src/git_it/repository_ingestion/composition.py src/git_it/repository_ingestion/interfaces/cli.py src/git_it/tools/registry.py tests/unit/test_list_analyses_cli.py tests/unit/test_tools_registry.py`

## Files changed

- `src/git_it/repository_ingestion/composition.py` — backend-aware commit analysis reader builder.
- `src/git_it/repository_ingestion/interfaces/cli.py` — `list-analyses` uses composition.
- `src/git_it/tools/registry.py` — MCP/chat tools use backend-aware readers and stores.
- `tests/unit/test_list_analyses_cli.py` — covers CLI delegation to the composition builder.
- `tests/unit/test_tools_registry.py` — covers registry delegation to backend-aware builders.
- `docs/architecture.md` — documents the persistence composition seam.
- `docs/progress/infrastructure/batch-95-persistence-backend-seam.md` — this file.
