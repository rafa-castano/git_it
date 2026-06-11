# Repository ingestion implementation progress

## Purpose

This document keeps a lightweight running summary of the main repository ingestion implementation batches.

It exists so the project can preserve the reasoning, examples, and incremental learning while the work advances, instead of reconstructing it at the end.

## Maintenance rule

Update this document after each meaningful implementation batch.

Each entry should include:

- batch goal,
- source of truth used,
- examples covered,
- tests added or updated,
- production behavior added,
- relevant follow-up.

## Batch 1 — Repository URL contract

### Goal

Define the smallest public contract for accepting repository URLs before any Git, network, or persistence work exists.

### Source of truth

- `specs/001-repository-ingestion.md`
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

## Batch 2 — Failure mapping

### Goal

Centralize ingestion failure status, error code, stage, and retryability rules.

### Source of truth

- `specs/001-repository-ingestion.md` failure mapping table

### Examples

```text
INVALID_URL -> FAILED_VALIDATION / VALIDATING_URL / retryable=false
REPOSITORY_NOT_FOUND -> FAILED_FETCH / FETCHING_METADATA / retryable=false
CLONE_TIMEOUT -> FAILED_FETCH / CLONING_OR_FETCHING / retryable=true
STORAGE_FAILED -> FAILED_PERSISTENCE / PERSISTING_FACTS / retryable=true
```

Dynamic examples require a caller-provided stage:

```text
LIMIT_EXCEEDED
INGESTION_TIMEOUT
CANCELLED_BY_USER
```

### Tests

Added unit tests for static mappings, dynamic mappings, missing dynamic stage, and unknown codes.

### Production behavior

Added `IngestionFailure` and `failure_for_error_code`.

### Follow-up

Application services should delegate failure classification to this mapper instead of duplicating status logic.

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

## Batch 4 — Application validation boundary

### Goal

Introduce the repository ingestion application service without real Git mining.

### Source of truth

- URL contract
- failure mapping
- no network/live repository default test policy

### Examples

Invalid input:

```text
not-a-url -> FAILED_VALIDATION / INVALID_URL / VALIDATING_URL
```

Unsupported host:

```text
https://gitlab.com/owner/repo -> FAILED_VALIDATION / UNSUPPORTED_URL / VALIDATING_URL
```

### Tests

Added service tests proving invalid URLs fail safely and do not call Git tooling.

### Production behavior

Added `RepositoryIngestionService`, `GitGateway` protocol, and `IngestionResult`.

### Follow-up

The service became the stable seam for CLI/query/API layers.

## Batch 5 — Valid URL starts clone/fetch lifecycle

### Goal

Make valid repository inputs cross the application boundary into the Git gateway using canonical URLs.

### Source of truth

- URL contract
- ingestion lifecycle stages from `specs/001-repository-ingestion.md`

### Examples

Both inputs call the gateway with the same canonical URL:

```text
https://github.com/owner/repo
https://github.com/owner/repo.git

=> https://github.com/owner/repo
```

### Tests

Added service tests for valid URL and `.git` suffix normalization.

### Production behavior

`RepositoryIngestionService.ingest` now calls `GitGateway.clone_or_fetch(canonical_url)` and returns `CLONING_OR_FETCHING` for the current lifecycle boundary.

### Follow-up

Future batches should replace the spy gateway with a safe local Git adapter contract, still without executing repository code.

## Batch 6 — Gateway failure mapping

### Goal

Convert controlled Git gateway failures into safe ingestion results.

### Source of truth

- failure mapping table in `specs/001-repository-ingestion.md`
- security requirement to avoid stack traces and unsafe details in user-facing failures

### Examples

```text
REPOSITORY_NOT_FOUND -> FAILED_FETCH / FETCHING_METADATA / retryable=false
CLONE_TIMEOUT -> FAILED_FETCH / CLONING_OR_FETCHING / retryable=true
```

### Tests

Added service tests using a fake failing gateway.

### Production behavior

Added `GitGatewayError` and service handling that maps gateway error codes through `failure_for_error_code`.

The safe message is:

```text
Repository fetch failed safely before analysis could start.
```

### Follow-up

The next batch should avoid inventing behavior for unknown gateway error codes unless the specification is updated. The current specification defines known error-code mappings but does not define an unknown-code fallback.

## Batch 7 — Known gateway failure coverage

### Goal

Ensure the application service covers every known fetch/Git gateway failure currently defined by the repository ingestion specification.

### Source of truth

- `specs/001-repository-ingestion.md` default failure mapping table

### Examples

```text
REPOSITORY_NOT_FOUND -> FAILED_FETCH / FETCHING_METADATA / retryable=false
REPOSITORY_PRIVATE_OR_INACCESSIBLE -> FAILED_FETCH / FETCHING_METADATA / retryable=false
METADATA_UNAVAILABLE -> FAILED_FETCH / FETCHING_METADATA / retryable=true
CLONE_TIMEOUT -> FAILED_FETCH / CLONING_OR_FETCHING / retryable=true
GIT_FETCH_FAILED -> FAILED_FETCH / CLONING_OR_FETCHING / retryable=true
```

### Tests

Expanded the service-level gateway failure parametrization to include all known fetch/Git failure codes.

This batch did not need production changes because the batch 6 implementation already delegated classification to `failure_for_error_code` instead of hard-coding individual cases. That is GOOD architecture: one mapper, one source of truth.

### Production behavior

No production code changed in this batch.

### Follow-up

Unknown gateway error-code behavior remains intentionally unspecified. Do not add a fallback until the spec defines whether unknown codes should fail fast for developers or become a safe generic failure for users.

## Batch 8 — Safe Git command planning

### Goal

Define the first safe Git adapter contract without executing Git, touching the network, or cloning any live repository.

### Source of truth

- `specs/001-repository-ingestion.md` MVP behavior
- `docs/security/threat-model.md`
- `docs/testing-strategy.md`

### Examples

Missing bare cache plans a safe bare clone:

```text
git -c protocol.file.allow=never clone --bare --no-checkout --no-recurse-submodules https://github.com/owner/repo <cache-path>
```

Existing bare cache plans a safe fetch:

```text
git --git-dir <cache-path> -c protocol.file.allow=never fetch --prune --tags --no-recurse-submodules origin +refs/heads/*:refs/heads/* +refs/tags/*:refs/tags/*
```

Both plans set:

```text
GIT_TERMINAL_PROMPT=0
GIT_LFS_SKIP_SMUDGE=1
```

### Tests

Added unit tests for clone and fetch command plans.

The tests assert:

- bare clone/fetch only,
- no checkout,
- no submodule recursion,
- Git LFS smudge is skipped,
- terminal credential prompting is disabled,
- default timeout is 300 seconds.

### Production behavior

Added `GitCommandPlan` and `plan_clone_or_fetch` in `safe_git.py`.

No subprocess execution exists yet. This is intentional: command construction is now reviewable and testable before any side effects are introduced.

### Follow-up

The next batch should connect this command planner to a subprocess runner boundary that translates timeout and Git failures into `GitGatewayError` without exposing raw stderr by default.

## Batch 9 — Safe Git runner boundary

### Goal

Connect the safe Git command planner to an injectable execution boundary without introducing real subprocess execution yet.

### Source of truth

- `specs/001-repository-ingestion.md` failure mappings
- `docs/security/threat-model.md` safe ingestion constraints
- Batch 8 command planning contract

### Examples

Successful runner result:

```text
GitCommandResult(exit_code=0) -> no gateway error
```

Timeout from runner:

```text
GitCommandTimeoutError -> GitGatewayError(error_code="CLONE_TIMEOUT")
```

Non-zero Git exit:

```text
GitCommandResult(exit_code=128) -> GitGatewayError(error_code="GIT_FETCH_FAILED")
```

### Tests

Added unit tests with fake runners only.

The tests assert:

- `SafeGitGateway` executes the planned command through an injected runner,
- timeout failures map to `CLONE_TIMEOUT`,
- non-zero Git exits map to `GIT_FETCH_FAILED`,
- user-facing exception text remains the safe generic fetch message.

### Production behavior

Added:

- `GitCommandResult`,
- `GitCommandTimeoutError`,
- `GitCommandRunner` protocol,
- `SafeGitGateway`.

No real `subprocess` runner exists yet. This keeps command execution reviewable and testable before touching the OS process boundary.

### Follow-up

The next batch can add a concrete subprocess runner with deterministic unit tests around argument forwarding, timeout handling, environment merging, and no raw stderr exposure.

## Batch 10 — Subprocess Git runner

### Goal

Add the concrete OS process runner boundary for Git commands while keeping tests deterministic and avoiding real Git execution.

### Source of truth

- Batch 8 safe command plans
- Batch 9 runner boundary
- security requirement to avoid raw stderr exposure by default

### Examples

A planned command is forwarded without shell execution:

```text
args=["git", "status"]
shell=False
check=False
capture_output=True
text=True
```

Environment is merged with the plan taking precedence:

```text
base: GIT_TERMINAL_PROMPT=1
plan: GIT_TERMINAL_PROMPT=0
result: GIT_TERMINAL_PROMPT=0
```

Timeouts are mapped without exposing captured stderr:

```text
subprocess.TimeoutExpired(stderr="secret") -> GitCommandTimeoutError
```

Non-zero process exits preserve only the exit code:

```text
returncode=128 -> GitCommandResult(exit_code=128)
```

### Tests

Added unit tests with an injected fake `run_command` callable.

The tests assert:

- command args are forwarded as a list,
- `shell=False`,
- `check=False`,
- stdout/stderr are captured but not exposed,
- timeout maps to `GitCommandTimeoutError`,
- non-zero return code is preserved as data.

### Production behavior

Added `SubprocessGitCommandRunner` plus protocols for subprocess return objects and callable injection.

The runner defaults to `subprocess.run`, but tests inject a fake callable. This keeps the production path real while the default test path remains local and deterministic.

### Follow-up

The next batch can wire `SubprocessGitCommandRunner` and `SafeGitGateway` into the application composition layer once the project has a concrete ingestion entry point or CLI factory.
