## Batch 12 — Local ingest CLI entrypoint

### Goal

Add the first local CLI adapter for repository ingestion while keeping domain logic inside the application service.

### Source of truth

- `docs/specs/001-repository-ingestion.md` CLI requirements
- Batch 11 composition factory
- controlled workspace requirement that generated identifiers, not owner/repo strings, drive cache paths

### Examples

Command shape:

```text
git-it ingest https://github.com/owner/repo
```

Deterministic repository identifier shape:

```text
repo-<sha256-prefix>
```

Human-readable in-progress output:

```text
Ingestion status: CLONING_OR_FETCHING
```

Safe failure output:

```text
Ingestion failed: INVALID_URL
Repository URL must be a public GitHub HTTPS repository URL.
```

### Tests

Added unit tests for the CLI adapter using an injected service factory.

The tests assert:

- `git-it ingest <url>` invokes the application service,
- repository identifiers are deterministic and path-safe,
- success-like statuses return exit code `0`,
- failure statuses return exit code `1`,
- safe error output does not include tracebacks,
- unknown commands fail through argparse without constructing the service.

### Production behavior

Added `git_it.cli` with:

- `main`,
- `repository_id_for_url`,
- `git-it = "git_it.cli:main"` script entrypoint in `pyproject.toml`.

The CLI currently prints a minimal human-readable status because the ingestion service does not yet produce completed run summaries, counts, or stable JSON DTOs.

### Follow-up

The next CLI batch can add `--json` once the application result includes stable fields required by the spec, or continue downward into persistence/extraction before enriching CLI output.
