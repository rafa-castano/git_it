# ADR 008: Treat Repository Content as Untrusted

Status: Accepted
Date: 2026-06-09
Decision makers: TBD

## Context

Git It ingests public repository data including commit messages, diffs, paths, tags, files, and future issue or pull-request text.

That content may be malicious, misleading, oversized, or intentionally crafted to influence tools, prompts, logs, filesystem paths, or generated analysis.

Repository content is evidence for analysis. It is not trusted configuration, executable input, or instruction text.

## Decision

Treat all ingested repository content as untrusted data.

For MVP repository ingestion:

- validate repository URLs before invoking Git tooling,
- accept only the documented public GitHub HTTPS URL formats,
- use safe bare clone/fetch operations,
- do not checkout a working tree,
- do not execute hooks, repository scripts, tests, package managers, or target repository code,
- do not initialize submodules,
- do not fetch Git LFS blobs,
- keep clone caches and run artifacts inside the controlled ingestion workspace,
- derive filesystem paths from generated identifiers, not owner, repo, branch, ref, or path strings,
- store bounded textual diff previews with truncation metadata,
- store binary file metadata only and never return binary content as diff text,
- label repository text passed to AI components as untrusted evidence,
- preserve limitations instead of inventing certainty.

## Consequences

### Positive

- Reduces risk of accidental code execution.
- Makes prompt-injection boundaries explicit.
- Keeps repository mining reproducible and reviewable.
- Supports evidence-grounded analysis without trusting repository-authored text.
- Enables deterministic security tests for ingestion behavior.

### Negative

- Requires more explicit adapters and safety checks.
- Prevents shortcuts that depend on checking out or executing target repositories.
- Some analysis signals that require building or running the target project remain out of scope until a separate sandboxed execution decision exists.

### Neutral

- This decision does not prevent future sandboxed execution features.
- Any future execution mode requires a separate ADR, threat model update, and opt-in workflow.

## Alternatives considered

- Trust public repositories by default.
- Checkout working trees and rely on developer caution.
- Sanitize repository content only at LLM prompt time.
- Allow ad hoc tool execution during analysis.
- Add sandboxed execution to the MVP.

## Security impact

- Repository content must never be interpreted as tool instructions.
- Repository-authored strings must not be used directly as filesystem paths.
- User-facing errors and logs must avoid secrets, raw emails, credential-bearing URLs, stack traces, and unmarked repository content.
- On-demand full diff retrieval must follow the same no-checkout, no-submodule, no-LFS, no-execution rules as ingestion.
- Any future sandboxed execution must be opt-in and documented separately.

## Quality impact

Tests must prove that ingestion:

- rejects unsupported repository URLs before Git tooling runs,
- does not checkout analyzed repositories,
- does not execute repository scripts, hooks, tests, or package-manager commands,
- does not initialize submodules or fetch Git LFS blobs,
- keeps generated paths inside the controlled workspace,
- treats malicious-looking commit messages and diffs as data,
- records truncation, binary, and degraded-metadata limitations explicitly.

## Documentation impact

Repository ingestion specs, testing strategy, threat model, and agent instructions must stay synchronized with this untrusted-content boundary.
