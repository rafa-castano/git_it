## Batch 3 — Workspace path safety

### Goal

Define safe local workspace paths before clone/fetch implementation.

### Source of truth

- controlled workspace lifecycle in `specs/001-repository-ingestion.md`
- local-first, no-container MVP strategy

### Examples

Repository cache:

```text
.data/git-it/ingestion/repos/{repository_id}.git
```

Run artifacts:

```text
.data/git-it/ingestion/runs/{ingestion_run_id}
```

Rejected identifiers:

```text
../outside
owner/repo
branch/name
""
.
..
```

### Tests

Added unit tests for root derivation, repository cache path derivation, run artifact path derivation, and unsafe identifier rejection.

### Production behavior

Added `ingestion_workspace_root`, `repository_cache_path`, `run_artifacts_path`, and `UnsafeWorkspaceIdentifierError`.

### Follow-up

The Git adapter must use these helpers instead of manually joining user-controlled path fragments.
