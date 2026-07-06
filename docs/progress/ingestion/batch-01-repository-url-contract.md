## Batch 1 — Repository URL contract

### Goal

Define the smallest public contract for accepting repository URLs before any Git, network, or persistence work exists.

### Source of truth

- `docs/specs/001-repository-ingestion.md`
- local-first MVP constraints
- public GitHub repository-only scope

### Examples

Accepted:

```text
https://github.com/owner/repo
https://github.com/owner/repo.git
```

Rejected safely:

```text
not-a-url
https://gitlab.com/owner/repo
https://github.com/owner
https://github.com/owner/repo/tree/main
```

### Tests

Added unit tests for URL parsing, canonicalization, and safe validation failures.

### Production behavior

Added `parse_repository_url`, `ParsedRepositoryUrl`, and `RepositoryUrlValidationError`.

The parser returns a canonical URL and rejects unsupported or malformed inputs with machine-readable error codes.

### Follow-up

Later CLI and API layers should reuse this contract instead of re-validating URLs differently.
