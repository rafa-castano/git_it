## Batch 11 — Repository ingestion composition

### Goal

Provide a small application composition factory that wires the ingestion service to the safe Git gateway and controlled workspace paths.

### Source of truth

- `docs/specs/001-repository-ingestion.md` application-service and controlled-workspace requirements
- Batch 3 workspace path helpers
- Batch 8-10 safe Git gateway and runner contracts

### Examples

For repository identifier `repo-123`, the clone cache path is derived as:

```text
.data/git-it/ingestion/repos/repo-123.git
```

A valid URL with `.git` suffix still reaches Git as canonical HTTPS:

```text
https://github.com/owner/repo.git -> https://github.com/owner/repo
```

Existing bare cache selects fetch planning instead of clone planning:

```text
git --git-dir <cache-path> ... fetch --prune --tags --no-recurse-submodules ...
```

### Tests

Added unit tests for composition using a fake `GitCommandRunner`.

The tests assert:

- the factory returns a working `RepositoryIngestionService`,
- the service uses the controlled repository cache path,
- valid URLs are canonicalized before reaching Git,
- existing bare cache paths select the fetch plan.

### Production behavior

Added `build_repository_ingestion_service` in `composition.py`.

The factory creates:

```text
RepositoryIngestionService -> SafeGitGateway -> GitCommandRunner
```

By default it uses `SubprocessGitCommandRunner`; tests can inject a fake runner.

### Follow-up

The next batch can add the local CLI adapter that calls this factory while keeping domain logic out of the CLI.
