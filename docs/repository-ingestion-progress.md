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

## Batch 11 — Repository ingestion composition

### Goal

Provide a small application composition factory that wires the ingestion service to the safe Git gateway and controlled workspace paths.

### Source of truth

- `specs/001-repository-ingestion.md` application-service and controlled-workspace requirements
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

## Batch 12 — Local ingest CLI entrypoint

### Goal

Add the first local CLI adapter for repository ingestion while keeping domain logic inside the application service.

### Source of truth

- `specs/001-repository-ingestion.md` CLI requirements
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

## Batch 13 — SQLite ingestion run store

### Goal

Add the first SQLite-backed persistence port for ingestion run audit records before enriching CLI summaries.

### Source of truth

- `specs/001-repository-ingestion.md` SQLite-backed fact persistence requirement
- `IngestionRun: append-only per ingestion attempt`
- failure persistence requirements for status, error code, stage, retryable flag, and safe message

### Examples

Successful run record:

```text
run_id=run-1
repository_id=repo-1
canonical_url=https://github.com/owner/repo
status=COMPLETED
started_at=2026-06-15T10:00:00Z
completed_at=2026-06-15T10:01:00Z
```

Failure run record:

```text
status=FAILED_FETCH
error_code=CLONE_TIMEOUT
error_stage=CLONING_OR_FETCHING
retryable=true
safe_message=Repository fetch failed safely before analysis could start.
```

Append-only behavior:

```text
repo-1 -> [run-1, run-2]
```

### Tests

Added unit tests using temporary SQLite databases.

The tests assert:

- ingestion run records round-trip through SQLite,
- failure details are persisted and restored,
- multiple runs for the same repository are retained instead of replacing each other,
- store methods return DTO/dataclass records, not SQLite rows.

### Production behavior

Added `storage.py` with:

- `IngestionRunRecord`,
- `SqliteIngestionRunStore`,
- schema initialization for `ingestion_runs`,
- save/get/list methods for ingestion run audit records.

This batch does not yet wire persistence into `RepositoryIngestionService`; it establishes the storage boundary first.

### Follow-up

The next batch can wire ingestion run creation/update into the application service or add a query service DTO over `SqliteIngestionRunStore` for future CLI/GUI summaries.

## Batch 14 — Repository ingestion architecture layers

### Goal

Refactor the repository ingestion package from a flat module layout into explicit internal architecture layers before adding more behavior.

### Source of truth

- Clean/hexagonal architecture principles
- feature-first package boundary around `repository_ingestion`
- existing specs requiring application services, stable ports, local CLI, Git safety, SQLite persistence, and future query/GUI readiness

### Problem found

The previous structure was feature-scoped but internally flat:

```text
repository_ingestion/
  application_service.py
  composition.py
  failure_mapping.py
  safe_git.py
  storage.py
  url_contract.py
  workspace_paths.py
```

That was acceptable while the feature was tiny, but it had started to mix concepts:

- domain policies sat next to infrastructure adapters,
- SQLite storage sat next to URL validation,
- the Git adapter imported `GitGatewayError` from the application service module,
- the CLI lived only as a top-level package module,
- future query/application work would make the flat package harder to navigate.

### Refactor applied

The package now keeps the feature boundary and adds internal layers:

```text
repository_ingestion/
  domain/
    failure_mapping.py
    url_contract.py
  application/
    ports.py
    service.py
  infrastructure/
    git.py
    sqlite.py
    workspace.py
  interfaces/
    cli.py
  composition.py
```

The top-level `git_it.cli` module remains as a thin script entrypoint wrapper for `pyproject.toml` compatibility.

### Examples

Domain code owns pure rules:

```text
parse_repository_url(...)
failure_for_error_code(...)
```

Application code owns use cases and ports:

```text
RepositoryIngestionService
GitGateway
GitGatewayError
```

Infrastructure code implements adapters:

```text
SafeGitGateway
SubprocessGitCommandRunner
SqliteIngestionRunStore
repository_cache_path(...)
```

Interface code owns CLI concerns:

```text
git-it ingest <url>
```

### Tests

Existing behavior tests were updated to import from the new layers.

Added architecture guard tests asserting:

- `domain` does not import application, infrastructure, interfaces, or composition,
- `application` does not import infrastructure, interfaces, or composition.

### Production behavior

No behavior change intended.

This was a structural refactor to preserve dependency direction:

```text
domain <- application <- infrastructure/interfaces
                  ^
                  |
             composition wires adapters
```

### Follow-up

The next behavior batch can continue with query DTOs or service-to-storage wiring using the new layer boundaries instead of adding more code to a flat package.

## Batch 15 — Ingestion run query DTOs

### Goal

Add the first stable query DTOs over persisted ingestion runs so future CLI/GUI adapters do not depend on SQLite rows or infrastructure records.

### Source of truth

- `specs/001-repository-ingestion.md` query service DTO requirements
- Batch 13 SQLite ingestion run store
- Batch 14 layered architecture boundaries

### Examples

Status DTO:

```text
get_ingestion_status("run-1") -> IngestionStatusDTO(
  run_id="run-1",
  status="FAILED_FETCH",
  error_code="CLONE_TIMEOUT",
  error_stage="CLONING_OR_FETCHING",
  retryable=true,
  safe_message="Repository fetch failed safely before analysis could start."
)
```

Run summary DTO:

```text
get_ingestion_run_summary("run-1") -> IngestionRunSummaryDTO(
  run_id="run-1",
  repository_id="repo-1",
  canonical_url="https://github.com/owner/repo",
  status="COMPLETED",
  started_at="2026-06-15T10:00:00Z",
  completed_at="2026-06-15T10:01:00Z"
)
```

Unknown run behavior:

```text
get_ingestion_status("missing-run") -> None
get_ingestion_run_summary("missing-run") -> None
```

### Tests

Added application query service tests with a fake reader.

Extended SQLite store tests to prove `SqliteIngestionRunStore` can back the application query service through structural typing.

The tests assert:

- query methods return stable DTO dataclasses,
- missing runs return `None`,
- application query service depends on a reader port/protocol rather than SQLite,
- SQLite store can satisfy that reader port without leaking SQLite rows upward.

### Production behavior

Added `application/query_service.py` with:

- `IngestionRunView` protocol,
- `IngestionRunReader` protocol,
- `IngestionStatusDTO`,
- `IngestionRunSummaryDTO`,
- `RepositoryIngestionQueryService`.

No CLI output changed yet.

### Follow-up

The next batch can either wire this query service into composition or connect `RepositoryIngestionService` to write ingestion run records so query DTOs have real application-generated data.

## Batch 16 — Application ingestion run persistence

### Goal

Wire ingestion run persistence into the application service through an application writer port, without making the service depend on SQLite.

### Source of truth

- `specs/001-repository-ingestion.md` ingestion run audit and failure persistence requirements
- Batch 13 SQLite ingestion run store
- Batch 14 architecture layers
- Batch 15 query DTO/read port

### Examples

Success-like current MVP result:

```text
status=CLONING_OR_FETCHING
run_id=run-1
canonical_url=https://github.com/owner/repo
completed_at=None
```

Validation failure:

```text
status=FAILED_VALIDATION
error_code=UNSUPPORTED_URL
error_stage=VALIDATING_URL
retryable=false
canonical_url=""
```

The empty canonical URL for invalid inputs is intentional: credential-bearing or malformed raw URLs must not be persisted as repository evidence.

Gateway failure:

```text
status=FAILED_FETCH
error_code=CLONE_TIMEOUT
error_stage=CLONING_OR_FETCHING
retryable=true
safe_message=Repository fetch failed safely before analysis could start.
```

### Tests

Added application-service tests with a fake run writer.

Extended composition tests to verify the default factory wires `RepositoryIngestionService` to `SqliteIngestionRunStore` under the controlled ingestion workspace.

The tests assert:

- service results include `run_id` when persistence is enabled,
- success-like results are recorded,
- validation failures are recorded without raw invalid URLs,
- Git gateway failures are recorded with mapped status/error/stage/retryable fields,
- composition stores runs in `.data/git-it/ingestion/git-it.sqlite3`.

### Production behavior

Added to `application/ports.py`:

- `IngestionRunRecord`,
- `IngestionRunWriter`.

Updated `RepositoryIngestionService` to optionally accept:

- `repository_id`,
- `run_writer`,
- `run_id_factory`,
- `clock`.

Updated `SqliteIngestionRunStore` to use the application-owned `IngestionRunRecord`.

Updated composition so the default local service persists ingestion runs to SQLite.

### Follow-up

The next batch can expose persisted run IDs in CLI output or use `RepositoryIngestionQueryService` to read back summaries after ingestion.

## Batch 17 — CLI run ID output

### Goal

Expose the persisted run ID in CLI output so the result of each ingestion is traceable without parsing SQLite directly.

### Source of truth

- `specs/001-repository-ingestion.md` CLI human-readable output requirements
- Batch 16 `IngestionResult.run_id` already populated by the application service

### Examples

Success-like status with run ID:

```text
Ingestion status: CLONING_OR_FETCHING
Run ID: run-abc123
```

Failure with run ID:

```text
Ingestion failed: INVALID_URL
Run ID: run-abc123
Repository URL must be a public GitHub HTTPS repository URL.
```

No run ID (persistence not wired):

```text
Ingestion status: CLONING_OR_FETCHING
```

### Tests

Added three CLI unit tests:

- `test_ingest_cli_prints_run_id_in_success_output_when_present` — asserts `Run ID: <id>` follows the status line when `run_id` is present.
- `test_ingest_cli_prints_run_id_in_failure_output_when_present` — asserts `Run ID: <id>` appears between the error code line and the safe message for failure statuses.
- `test_ingest_cli_omits_run_id_line_when_run_id_is_absent` — asserts no `Run ID:` line when `run_id` is `None`.

### Production behavior

Updated `_print_ingestion_result` in `interfaces/cli.py` to print `Run ID: <run_id>` after the status/error line when `run_id` is not `None`.

No other modules changed. The `run_id` was already available on `IngestionResult` since Batch 16.

### Follow-up

The next batch can enrich the success output with more spec-required fields (repository, canonical URL, status, counts, limitations) or begin the commit extraction and persistence layer.

## Batch 18 — CLI success output with repository identity

### Goal

Enrich the CLI success output with repository identity (owner/repo and canonical URL) so the result of each ingestion is traceable without reading persisted records directly.

### Source of truth

- `specs/001-repository-ingestion.md` CLI human-readable output requirements (section 10)
- `ParsedRepositoryUrl.canonical_url` already computed inside the service during URL validation

### Examples

Success output with repository identity:

```text
Ingestion status: CLONING_OR_FETCHING
Repository: owner/repo
Canonical URL: https://github.com/owner/repo
Run ID: run-abc123
```

No repository lines when canonical URL is absent (e.g. validation failure path):

```text
Ingestion failed: INVALID_URL
Run ID: run-abc123
Repository URL must be a public GitHub HTTPS repository URL.
```

### Tests

Added service tests:

- `test_ingestion_service_includes_canonical_url_in_success_like_result` — verifies `canonical_url` is set on success-like results.
- `test_ingestion_service_normalizes_canonical_url_by_stripping_git_suffix` — verifies `.git` suffix does not appear in `canonical_url`.
- `test_ingestion_service_canonical_url_is_none_for_validation_failure` — verifies validation failures leave `canonical_url` as `None`.

Added CLI tests:

- `test_ingest_cli_prints_repository_and_canonical_url_in_success_output` — asserts both lines appear when `canonical_url` is present.
- `test_ingest_cli_omits_repository_lines_when_canonical_url_is_absent` — asserts neither line appears when `canonical_url` is `None`.

### Production behavior

Added `canonical_url: str | None = None` to `IngestionResult` in `application/service.py`.

Populated `canonical_url` for both the gateway-failure and success-like paths (where a valid `ParsedRepositoryUrl` is available). Validation failures leave it `None`.

Updated `_print_ingestion_result` in `interfaces/cli.py` to print `Repository: owner/repo` and `Canonical URL: ...` immediately after the status line, only when `canonical_url` is present. `owner/repo` is derived by stripping the `https://github.com/` prefix from the validated canonical URL.

### Follow-up

The next batch can begin the commit extraction and persistence layer, or add counts and limitations to the CLI output once commit extraction is wired.

## Batch 19 — Commit extraction port + service wires extractor

### Goal

Establish the commit extraction contract so the service can receive and count raw commits after a successful clone/fetch, without coupling the application layer to GitPython or any concrete implementation.

### Source of truth

- `specs/001-repository-ingestion.md` commit evidence requirements (section 8)
- Clean architecture boundary: domain holds the data record, application holds the port protocol

### Examples

Service wired with a fake extractor returning 3 commits:

```text
result.commits_extracted == 3
```

Service with no extractor:

```text
result.commits_extracted is None
```

Gateway failure does not trigger extraction:

```text
extractor.call_count == 0
```

CLI success with count:

```text
Ingestion status: CLONING_OR_FETCHING
Repository: owner/repo
Canonical URL: https://github.com/owner/repo
Commits: 3 extracted
Run ID: run-abc123
```

### Tests

Added service tests:

- `test_ingestion_service_extracts_commits_after_successful_clone_or_fetch` — extractor is called once and its count is set on the result.
- `test_ingestion_service_skips_extraction_when_no_extractor_is_wired` — `commits_extracted` is `None` when no extractor is injected.
- `test_ingestion_service_does_not_extract_commits_on_gateway_failure` — extractor is never called on git gateway failure.

Added CLI tests:

- `test_ingest_cli_prints_commit_count_in_success_output_when_present` — `Commits: N extracted` appears when `commits_extracted` is set.
- `test_ingest_cli_omits_commit_count_when_absent` — no `Commits:` line when `commits_extracted` is `None`.

### Production behavior

Added `domain/commits.py` with `ExtractedCommit` (sha, committed_at, message, author_name, committer_name, parent_shas).

Added `CommitExtractor` protocol to `application/ports.py` with `extract_commits() -> list[ExtractedCommit]`.

Updated `IngestionResult` with `commits_extracted: int | None = None`.

Updated `RepositoryIngestionService.__init__` to accept `commit_extractor: CommitExtractor | None = None` and call it after a successful clone/fetch.

Updated `_print_ingestion_result` to print `Commits: N extracted` before the Run ID line when the count is present.

Composition unchanged — extractor remains unwired until a real GitPython implementation exists.

### Follow-up

The next batch can add the GitPython-backed `CommitExtractor` implementation in `infrastructure/`, wire it into composition, and start proving real commit counts against a local fixture repository.

## Batch 20 — GitPython commit extractor wired into composition

### Goal

Add the first real commit extraction implementation using GitPython and prove it works against a local deterministic fixture, without any network access.

### Source of truth

- `specs/001-repository-ingestion.md` commit evidence requirements (section 8)
- Testing strategy: default tests must not require network access
- `CommitExtractor` protocol established in Batch 19

### Examples

Bare fixture repo with 3 commits:

```text
GitPythonCommitExtractor(cache_path=bare_path).extract_commits()
→ [ExtractedCommit(sha="...", message="third commit", ...), ...]  # reverse chronological
```

Composition with default extractor:

```text
result.commits_extracted == 2  # matches fixture commit count
```

### Tests

New test file `tests/unit/test_git_commit_extractor.py`:

- `test_git_commit_extractor_returns_all_commits_from_bare_repo` — count matches fixture.
- `test_git_commit_extractor_returns_commits_in_reverse_chronological_order` — latest commit first.
- `test_git_commit_extractor_populates_required_fields` — SHA length, message, author, committer.
- `test_git_commit_extractor_records_parent_shas` — parent SHA chain and initial commit has no parents.

Updated `tests/unit/test_repository_ingestion_composition.py`:

- Existing three tests inject `NullCommitExtractor` to avoid opening a non-existent repo.
- New `test_build_repository_ingestion_service_wires_gitpython_extractor_by_default` — pre-populates the cache path with a fixture bare repo and verifies `result.commits_extracted == 2`.

### Production behavior

Added `infrastructure/commits.py` with `GitPythonCommitExtractor`:
- Opens the bare clone at `cache_path` using `git.Repo`.
- Iterates `HEAD` commits via `repo.iter_commits()`.
- Maps each commit to `ExtractedCommit` (sha, committed_at, message, author_name, committer_name, parent_shas).
- Returns commits in reverse chronological order (GitPython default).

Updated `composition.py`:
- Added `commit_extractor: CommitExtractor | None = None` override parameter (pattern mirrors `runner`).
- Default creates `GitPythonCommitExtractor(cache_path=cache_path)`.

### Follow-up

The next step is to add SQLite persistence for commit facts (`CommitFact` store) so that re-ingestion can report inserted vs reused counts rather than just extracted counts.

## Batch 21 — Commit fact SQLite persistence and idempotent inserted/reused counts

### Goal

Persist extracted commits into SQLite using idempotent `INSERT OR IGNORE` so that re-ingestion reports inserted vs reused counts instead of just extracted counts.

### Source of truth

- `specs/001-repository-ingestion.md` commit fact persistence and idempotency requirements
- Batch 20 `CommitExtractor` protocol and `GitPythonCommitExtractor`
- `CommitFact` unique by `(repository_id, sha)` — re-ingestion must produce distinct inserted/reused tallies

### Examples

First ingestion of a repository with 3 commits:

```text
Ingestion status: CLONING_OR_FETCHING
Repository: owner/repo
Canonical URL: https://github.com/owner/repo
Commits: 3 inserted, 0 reused
Run ID: run-abc123
```

Re-ingestion of the same repository (all commits already present):

```text
Commits: 0 inserted, 3 reused
```

Mixed re-ingestion (1 new commit since last run):

```text
Commits: 1 inserted, 3 reused
```

Same SHA in two different repositories is treated as two distinct facts:

```text
repo-1 / sha-aaa -> inserted=1
repo-2 / sha-aaa -> inserted=1  # independent
```

### Tests

New test file `tests/unit/test_commit_fact_store.py`:

- `test_sqlite_commit_fact_store_inserts_new_commits` — 3 new commits → inserted=3, reused=0.
- `test_sqlite_commit_fact_store_marks_existing_commits_as_reused_on_reingest` — same 3 commits re-saved → inserted=0, reused=3.
- `test_sqlite_commit_fact_store_tracks_mixed_insertions_and_reuses` — 2 existing + 1 new → inserted=1, reused=2.
- `test_sqlite_commit_fact_store_treats_same_sha_as_independent_across_repositories` — same SHA in two repos both count as inserted.

Updated `tests/unit/test_repository_ingestion_service.py`:

- Renamed `test_ingestion_service_extracts_commits_after_successful_clone_or_fetch` to `test_ingestion_service_calls_extractor_after_successful_clone_or_fetch` — now only asserts the extractor is called once.
- Added `test_ingestion_service_persists_commits_and_reports_inserted_reused` — fake extractor + fake writer → `commits_inserted=2`, `commits_reused=1` on the result.
- Added `test_ingestion_service_does_not_report_counts_without_fact_writer` — extractor present but no writer → both counts are `None`.
- Updated `test_ingestion_service_skips_extraction_when_no_extractor_is_wired` — checks `commits_inserted is None` and `commits_reused is None`.

Updated `tests/unit/test_repository_ingestion_cli.py`:

- `test_ingest_cli_prints_commit_count_in_success_output_when_present` — now uses `commits_inserted=3, commits_reused=2` and asserts `Commits: 3 inserted, 2 reused`.
- `test_ingest_cli_omits_commit_count_when_absent` — uses `commits_inserted=None, commits_reused=None` and asserts no `Commits:` line.

Updated `tests/unit/test_repository_ingestion_composition.py`:

- `test_build_repository_ingestion_service_wires_gitpython_extractor_by_default` — now asserts `commits_inserted == 2` and `commits_reused == 0` instead of the removed `commits_extracted`.

### Production behavior

Added to `application/ports.py`:

- `CommitPersistenceResult` frozen dataclass with `inserted: int` and `reused: int`.
- `CommitFactWriter` protocol with `save_commit_facts(commits, *, repository_id) -> CommitPersistenceResult`.

Updated `IngestionResult` in `application/service.py`:

- Replaced `commits_extracted: int | None` with `commits_inserted: int | None` and `commits_reused: int | None`.

Updated `RepositoryIngestionService`:

- Accepts `commit_fact_writer: CommitFactWriter | None = None`.
- After extraction, calls `save_commit_facts` if writer is wired and populates both count fields.
- When no writer is wired, both counts remain `None`.

Added `SqliteCommitFactStore` to `infrastructure/sqlite.py`:

- `commit_facts` table with `UNIQUE(repository_id, sha)` constraint.
- `save_commit_facts` uses `INSERT OR IGNORE`; `rowcount == 1` → inserted, `rowcount == 0` → reused.
- `parent_shas` serialized as a JSON array.
- `initialize()` creates parent directories and the table idempotently.

Updated `_print_ingestion_result` in `interfaces/cli.py`:

- Prints `Commits: N inserted, M reused` when both `commits_inserted` and `commits_reused` are not `None`.

Updated `composition.py`:

- Added `commit_fact_writer: CommitFactWriter | None = None` override parameter.
- Creates `SqliteCommitFactStore` pointing to the same `git-it.sqlite3` database as the run store.
- Passes it as `commit_fact_writer` to `RepositoryIngestionService` by default.

### Follow-up

The next batch should add file-level change persistence and fix the final ingestion status from CLONING_OR_FETCHING to COMPLETED.

## Batch 22 — COMPLETED status + file change extraction and persistence

### Goal

Fix the final ingestion status from the intermediate `CLONING_OR_FETCHING` to `COMPLETED`, add file-level change extraction per commit using GitPython stats, persist them idempotently in a `file_facts` table, and expose inserted/reused counts in CLI output.

### Source of truth

- `specs/001-repository-ingestion.md` file-level evidence and completion status requirements
- `ExtractedCommit.file_changes` derived from `commit.stats.files` (GitPython)
- `UNIQUE(repository_id, commit_sha, file_path)` idempotency key

### Examples

First ingestion of a repository with 2 commits each touching 1 file:

```text
Ingestion status: COMPLETED
Repository: owner/repo
Canonical URL: https://github.com/owner/repo
Commits: 2 inserted, 0 reused
Files: 2 inserted, 0 reused
Run ID: run-abc123
```

Re-ingestion (no new commits):

```text
Commits: 0 inserted, 2 reused
Files: 0 inserted, 2 reused
```

### Tests

New test file `tests/unit/test_file_fact_store.py`:

- `test_sqlite_file_fact_store_inserts_new_file_facts` — 3 file facts across 2 commits → inserted=3, reused=0.
- `test_sqlite_file_fact_store_marks_existing_file_facts_as_reused_on_reingest` — same facts re-saved → inserted=0, reused=2.
- `test_sqlite_file_fact_store_tracks_mixed_insertions_and_reuses` — 1 new file + 1 existing → inserted=1, reused=1.
- `test_sqlite_file_fact_store_treats_same_file_as_independent_across_repositories` — same (sha, path) in two repos → both inserted.
- `test_sqlite_file_fact_store_skips_commits_with_no_file_changes` — empty file_changes → inserted=0, reused=0.

Updated `tests/unit/test_git_commit_extractor.py`:

- `test_git_commit_extractor_populates_file_changes_per_commit` — each fixture commit adds one .txt file; asserts `file_changes` has 1 entry with non-negative insertions/deletions.

Updated `tests/unit/test_repository_ingestion_service.py`:

- All success-path status assertions changed from `"CLONING_OR_FETCHING"` to `"COMPLETED"`.
- `test_ingestion_service_persists_success_like_run_result` — run record now has `status="COMPLETED"` and `completed_at` set (not `None`).
- `test_ingestion_service_persists_file_facts_and_reports_counts` — fake file fact writer returns `(inserted=5, reused=1)`; asserts on result fields.
- `test_ingestion_service_does_not_report_file_counts_without_file_fact_writer` — no writer → `files_inserted is None`, `files_reused is None`.

Updated `tests/unit/test_repository_ingestion_cli.py`:

- All `status="CLONING_OR_FETCHING"` changed to `status="COMPLETED"`.
- `test_ingest_cli_prints_file_count_in_success_output_when_present` — `Files: 7 inserted, 2 reused` in output.
- `test_ingest_cli_omits_file_count_when_absent` — no `Files:` line when both counts are `None`.

Updated `tests/unit/test_repository_ingestion_composition.py`:

- All `status == "CLONING_OR_FETCHING"` changed to `"COMPLETED"`.
- `test_build_repository_ingestion_service_wires_gitpython_extractor_by_default` — also asserts `files_inserted >= 2`.

### Production behavior

Updated `domain/commits.py`:

- Added `ExtractedFileChange` frozen dataclass with `path`, `insertions`, `deletions`.
- Added `file_changes: tuple[ExtractedFileChange, ...] = field(default_factory=tuple)` to `ExtractedCommit`.

Updated `application/ports.py`:

- Added `FileFactWriter` protocol with `save_file_facts(commits, *, repository_id) -> CommitPersistenceResult`.

Updated `application/service.py`:

- `IngestionResult` gains `files_inserted: int | None = None` and `files_reused: int | None = None`.
- `RepositoryIngestionService` accepts `file_fact_writer: FileFactWriter | None = None`.
- Success path status changed to `"COMPLETED"`.
- Success path `completed_at` now set to `self._clock()` instead of `None`.
- After commit persistence, calls `save_file_facts` if writer is wired.

Updated `infrastructure/commits.py`:

- `GitPythonCommitExtractor` extracts file changes via `commit.stats.files` → `ExtractedFileChange` tuples.
- `_extract_file_changes` wraps stats access in a bare `except` to avoid surfacing Git errors as exceptions.

Added `SqliteFileFactStore` to `infrastructure/sqlite.py`:

- `file_facts` table with `UNIQUE(repository_id, commit_sha, file_path)`.
- `save_file_facts` iterates commits → file_changes, uses `INSERT OR IGNORE`.

Updated `interfaces/cli.py`:

- Prints `Files: N inserted, M reused` when both counts are not `None`.

Updated `composition.py`:

- Adds `file_fact_writer: FileFactWriter | None = None` override parameter.
- Creates `SqliteFileFactStore` pointing to the same `git-it.sqlite3`.
- Wires it as default `file_fact_writer` in `RepositoryIngestionService`.

### Follow-up

The next batch should add the commit read path (query service + SQLite reader) so the analysis pipeline can access ingested commits without reading the DB directly.

## Batch 23 — Commit query service and `git-it commits` CLI command

### Goal

Add the commit read path so the rest of the pipeline (analysis, pattern detection, narrative) can query ingested commits through a stable application service rather than touching SQLite directly.

### Source of truth

- `specs/001-repository-ingestion.md` query service DTO requirements
- `specs/002-commit-analysis.md` — commit analysis requires reading commits back
- Layered architecture: `CommitRecord` DTO lives in application, `SqliteCommitReader` in infrastructure

### Examples

CLI commit listing:

```text
$ git-it commits https://github.com/owner/repo
abc1234  2026-01-15  Add user authentication  (Alice)
def5678  2026-01-14  Fix login bug  (Bob)
```

Empty repository:

```text
No commits stored for this repository. Run 'git-it ingest <url>' first.
```

With limit:

```text
$ git-it commits --limit 5 https://github.com/owner/repo
```

### Tests

New `tests/unit/test_sqlite_commit_reader.py`:

- `test_sqlite_commit_reader_returns_empty_list_when_no_commits_stored`
- `test_sqlite_commit_reader_returns_commits_for_repository`
- `test_sqlite_commit_reader_returns_commits_in_reverse_chronological_order`
- `test_sqlite_commit_reader_limits_result_when_limit_is_specified`
- `test_sqlite_commit_reader_isolates_commits_by_repository`

New `tests/unit/test_repository_commit_query_service.py`:

- `test_list_commits_delegates_to_reader`
- `test_list_commits_passes_limit_to_reader`
- `test_list_commits_returns_empty_list_when_reader_has_none`

New `tests/unit/test_commits_cli.py`:

- `test_commits_cli_prints_recent_commits` — sha[:7], message, author in output.
- `test_commits_cli_shows_message_when_no_commits_stored` — "No commits" line.
- `test_commits_cli_passes_limit_to_query_service` — `--limit 5` propagated to service.

### Production behavior

New `application/commit_query_service.py`:

- `CommitRecord` frozen dataclass (repository_id, sha, committed_at, message, author_name, committer_name, parent_shas).
- `CommitReader` protocol with `list_commits_for_repository(repository_id, *, limit=None)`.
- `RepositoryCommitQueryService` with `list_commits(repository_id, *, limit=None)`.

Added `SqliteCommitReader` to `infrastructure/sqlite.py`:

- SELECTs from `commit_facts` by `repository_id` ordered by `committed_at DESC`.
- Supports optional `LIMIT`.
- Deserializes `parent_shas` from JSON array.

Updated `composition.py`:

- Added `build_repository_commit_query_service(*, project_root)` factory.

Updated `interfaces/cli.py`:

- Added `commits` subparser with `--limit` (default 20).
- Added `CommitQueryFactory` protocol and `_default_commit_query_factory`.
- Added `_run_commits` and `_print_commits` helpers.
- `main` gains `commit_query_factory` injectable parameter for testability.

### Follow-up

The next batch implements `git-it analyze <url>` using a provider-agnostic LLM client backed by LiteLLM.

## Batch 24 — Provider-agnostic LLM client and `git-it analyze` command

### Goal

Add a provider-agnostic LLM abstraction and the first working end-to-end analysis command. A user who has run `git-it ingest <url>` can now run `git-it analyze <url>` to get an AI-generated case study from the ingested commit history.

### Source of truth

- `specs/002-commit-analysis.md` — commit analysis goals and security requirements
- `litellm` is already in `pyproject.toml` — single adapter for all providers
- Security requirement: commit messages must be treated as untrusted data (prompt injection protection)

### Examples

```text
$ git-it analyze https://github.com/owner/repo
Analysis (47 commits)
============================================================
## Summary
This repository implements a REST API with progressive feature additions...

## Key Technical Decisions
- Moved from synchronous to async request handling in batch 3...
```

With a different model:

```text
$ git-it analyze --model openai/gpt-4o-mini https://github.com/owner/repo
$ git-it analyze --model gemini/gemini-1.5-flash https://github.com/owner/repo
$ git-it analyze --model ollama/llama3.2 https://github.com/owner/repo
```

With commit limit:

```text
$ git-it analyze --limit 100 https://github.com/owner/repo
```

No commits stored:

```text
No commits stored for this repository. Run 'git-it ingest <url>' first.
```

### Tests

New `tests/unit/test_repository_analysis_service.py`:

- `test_analysis_service_calls_llm_with_commit_data` — sha, message, and author appear in LLM call.
- `test_analysis_service_returns_analysis_result` — `AnalysisResult` with correct `commit_count` and `analysis`.
- `test_analysis_service_passes_limit_to_reader` — limit propagated.
- `test_analysis_service_returns_empty_result_when_no_commits_stored` — no LLM call when zero commits.
- `test_analysis_service_system_prompt_marks_commit_data_as_untrusted` — system message contains "untrusted"/"user input"/"user data".
- `test_analysis_service_commit_messages_appear_only_in_data_section` — malicious message inside `[REPOSITORY DATA]` tags in user message.

New `tests/unit/test_analyze_cli.py`:

- `test_analyze_cli_prints_analysis_text`
- `test_analyze_cli_shows_commit_count`
- `test_analyze_cli_shows_no_commits_message_when_count_is_zero`
- `test_analyze_cli_passes_model_flag_to_factory`
- `test_analyze_cli_passes_limit_to_service`

### Production behavior

Added `LLMMessage` frozen dataclass and `LLMClient` protocol to `application/ports.py`.

New `application/analysis_service.py`:

- `AnalysisResult` frozen dataclass (repository_id, commit_count, analysis).
- `RepositoryAnalysisService` with `analyze(repository_id, *, limit=50)`.
- System prompt marks all `[REPOSITORY DATA]` as untrusted user input (prompt injection protection).
- Builds user message with commit shas, dates, authors, first-line messages — all within `[REPOSITORY DATA]` / `[/REPOSITORY DATA]` tags.
- Returns empty `AnalysisResult` without calling LLM when no commits are found.

New `infrastructure/llm.py`:

- `LiteLLMLLMClient` — wraps `litellm.completion()`.
- `litellm` import is deferred inside `complete()` to avoid import-time side effects.
- Model string follows LiteLLM format: `anthropic/claude-haiku-4-5-20251001`, `openai/gpt-4o-mini`, `gemini/gemini-1.5-flash`, `ollama/llama3.2`, etc.

Updated `composition.py`:

- Added `build_repository_analysis_service(*, project_root, model, llm_client=None)`.

Updated `interfaces/cli.py`:

- Added `analyze` subparser with `--model` (default: `anthropic/claude-haiku-4-5-20251001`) and `--limit` (default: 50).
- Added `AnalysisFactory` protocol and `_default_analysis_factory`.
- `main` gains `analysis_factory` injectable parameter.
- `_run_analyze` and `_print_analysis_result` helpers.

### Follow-up

The next batch can add structured `CommitAnalysis` output (per spec 002 schema) using Pydantic + instructor, or begin pattern detection (spec 003) over the stored commit and file facts.

## Batch 25 — structured per-commit analysis (spec 002)

### Goal

Implement `CommitAnalysis` domain model and `CommitAnalysisService` that produces structured, evidence-grounded per-commit interpretations using `instructor` + `litellm`.

### Source of truth

- `specs/002-commit-analysis.md`

### Examples covered

- `CommitCategory` enum: feature, bugfix, refactor, test, docs, build, security, performance, chore, unknown
- `RiskLevel` enum: low, medium, high, unknown
- `confidence` validated as float in [0.0, 1.0] by Pydantic `Field(ge=0.0, le=1.0)`
- `EvidenceRef` with optional `file_path` and `quote`
- Prompt injection: commit messages wrapped in `[REPOSITORY DATA]` / `[/REPOSITORY DATA]`; system prompt marks them as untrusted

### Tests added

- `tests/unit/test_commit_analysis_domain.py` — 7 tests (schema validation, enum coverage, confidence bounds)
- `tests/unit/test_commit_analysis_service.py` — 7 tests (LLM call count, message content, REPOSITORY tags, untrusted data marking, result forwarding, batch behavior)
- `tests/unit/test_analyze_commits_cli.py` — 4 tests (exit code, no-commits message, output content, limit forwarding)

### Production behavior added

- `domain/analysis.py` — `CommitCategory`, `RiskLevel`, `EvidenceRef`, `CommitAnalysis` Pydantic model
- `application/ports.py` — `CommitAnalysisClient` Protocol
- `application/commit_analysis_service.py` — `CommitAnalysisService` with `analyze_commit` and `analyze_commits` methods
- `infrastructure/llm.py` — `InstructorCommitAnalysisAdapter` using `instructor.from_litellm`
- `composition.py` — `build_commit_analysis_service()`
- `interfaces/cli.py` — `analyze-commits <url> [--model MODEL] [--limit N]` subcommand

### Follow-up

Pattern detection (spec 003) can now consume `CommitAnalysis` records. Consider persisting analyses to SQLite for reuse before pattern detection runs.

## Batch 26 — rule-based hotspot pattern detection (spec 003)

### Goal

Implement the first pattern detector: hotspot detection using aggregated file change data already stored in `file_facts`. No LLM required — pure SQL aggregation.

### Source of truth

- `specs/003-pattern-detection.md` (layer 1: rule-based detectors)

### Examples covered

- Files changed in N or more distinct commits are classified as hotspots
- Hotspots sorted by `commit_count` descending
- `churn = total_insertions + total_deletions`
- Results isolated by `repository_id`
- Empty result when no file facts stored

### Tests added

- `tests/unit/test_pattern_detection_service.py` — 8 tests (threshold, sorting, churn, empty repo, repo isolation via reader)
- `tests/unit/test_sqlite_file_fact_reader.py` — 5 tests (aggregation, distinct commit count, repo isolation, sort order)
- `tests/unit/test_patterns_cli.py` — 4 tests (exit code, no-data message, output content, threshold forwarding)

### Production behavior added

- `domain/patterns.py` — `Hotspot` (frozen dataclass with `churn` property), `PatternReport`
- `application/ports.py` — `FileChurnRecord`, `FileFactReader` Protocol
- `application/pattern_detection_service.py` — `PatternDetectionService.detect(hotspot_threshold=5)`
- `infrastructure/sqlite.py` — `SqliteFileFactReader` with GROUP BY + COUNT(DISTINCT commit_sha) query
- `composition.py` — `build_pattern_detection_service()`
- `interfaces/cli.py` — `patterns <url> [--hotspot-threshold N]` subcommand

### Follow-up

Next patterns to add: bugfix recurrence (multiple bugfix CommitAnalyses for same component) and refactor wave (cluster of refactor commits in a time window). These require stored CommitAnalysis records.

## Batch 27 — CommitAnalysis persistence + narrative engine + case-study command

### Goal

Complete the MVP pipeline: persist structured commit analyses to SQLite (so LLM is not called repeatedly), implement the narrative engine that synthesizes analyses and hotspot data into an educational case study, and expose a `case-study` CLI command.

### Source of truth

- `specs/002-commit-analysis.md` (persistence)
- `specs/004-narrative-engine.md`

### Examples covered

- `SqliteCommitAnalysisStore`: INSERT OR IGNORE idempotency; JSON serialization via `model_dump_json()` / `model_validate_json()`; `get_analysis`, `list_analyses` with optional limit
- `CommitAnalysisService` caching: skips LLM call when analysis already in store; saves new analyses when writer provided; does not re-save cached analyses
- `NarrativeService`: empty analyses → returns empty result without LLM call; commit summaries + hotspot files included in prompt; data wrapped in `[REPOSITORY DATA]` tags (prompt injection); system prompt marks data as untrusted
- `case-study` CLI: exits 0; prints narrative; "No analyses" message when none; passes model to factory

### Tests added

- `tests/unit/test_sqlite_commit_analysis_store.py` — 7 tests
- `tests/unit/test_commit_analysis_service_cache.py` — 3 tests
- `tests/unit/test_narrative_service.py` — 7 tests
- `tests/unit/test_case_study_cli.py` — 4 tests

### Production behavior added

- `application/ports.py` — `CommitAnalysisWriter`, `CommitAnalysisReader` Protocols
- `infrastructure/sqlite.py` — `SqliteCommitAnalysisStore` (implements both protocols)
- `application/commit_analysis_service.py` — optional `analysis_writer` + `analysis_reader` params; cache-aware `analyze_commits`
- `application/narrative_service.py` — `NarrativeResult`, `NarrativeService` (reads analyses + file churn, calls LLM with untrusted-data-tagged prompt)
- `composition.py` — `build_commit_analysis_service` now wires `SqliteCommitAnalysisStore`; `build_narrative_service()`
- `interfaces/cli.py` — `case-study <url> [--model MODEL]` subcommand; `NarrativeFactory`, `NarrativeGeneratorService` protocols

### MVP status

The full pipeline is now wired:
1. `git-it ingest <url>` — clone/fetch repo, persist commit facts + file facts to SQLite
2. `git-it analyze-commits <url>` — per-commit structured analysis with caching
3. `git-it patterns <url>` — rule-based hotspot detection from file facts
4. `git-it case-study <url>` — narrative synthesis from stored analyses + hotspots

### Follow-up

- Add bugfix recurrence and refactor wave detectors (spec 003) that read from `commit_analyses`
- Improve narrative structure: timeline, architectural transitions, learning lessons
- Add `list analyses` CLI command to inspect stored analyses

## Batch 28 — Pattern service linked into narrative engine

### Goal

Make `case-study` and `patterns` consume the same hotspot data: same threshold, same ordering, same source of truth.

### Source of truth

- `specs/004-narrative-engine.md`

### Examples covered

- `NarrativeService` now calls `pattern_service.detect()` (via `HotspotDetector` Protocol) instead of reading raw file churn directly
- `hotspot_count` in `NarrativeResult` now reflects files above threshold, not total files with any churn

### Tests added / updated

- `tests/unit/test_narrative_service.py` — replaced `FakeFileFactReader` with `FakePatternService`; added `test_generate_calls_pattern_service_detect`, `test_generate_hotspot_count_reflects_pattern_report`

### Production behavior added

- `application/narrative_service.py` — replaced `file_fact_reader` dependency with `pattern_service: HotspotDetector` Protocol
- `composition.py` — `build_narrative_service` wires `build_pattern_detection_service` output

## Batch 29 — Semantic pattern detection

### Goal

Extend `PatternDetectionService` with semantic patterns derived from stored `CommitAnalysis` records: category distribution and bugfix-prone components.

### Source of truth

- `specs/003-pattern-detection.md`

### Examples covered

- Category distribution: counts commits per `CommitCategory`, sorted by frequency
- Bugfix recurrence: components appearing in 2+ BUGFIX commits (uses `affected_components` from `CommitAnalysis`)
- `PatternDetectionService` accepts optional `analysis_reader`; falls back to pure churn detection when absent
- `NarrativeService._build_user_message` now receives full `PatternReport` and includes category counts and bugfix recurrences in LLM context

### Tests added

- `tests/unit/test_semantic_pattern_detection.py` — 7 tests

### Production behavior added

- `domain/patterns.py` — `CategoryCount`, `BugfixRecurrence` frozen dataclasses; `PatternReport` extended with `category_counts`, `bugfix_recurrences`
- `application/pattern_detection_service.py` — optional `analysis_reader`; `_compute_category_counts`, `_compute_bugfix_recurrences`
- `application/narrative_service.py` — `_build_user_message` takes full `PatternReport`; adds Category Distribution and Bugfix-Prone Components sections
- `composition.py` — `build_pattern_detection_service` wires `SqliteCommitAnalysisStore` as `analysis_reader`
- `interfaces/cli.py` — `_print_pattern_report` shows category counts and bugfix-prone components

## Batch 30 — Refactor wave detection and spec 004 narrative structure

### Goal

Add refactor wave pattern detector and align narrative system prompt to spec 004 section structure.

### Source of truth

- `specs/003-pattern-detection.md`
- `specs/004-narrative-engine.md`

### Examples covered

- Refactor wave detected when REFACTOR commits >= threshold (default 3); reports count and ratio
- System prompt now requests: Overview → Timeline → Main Components Through Time → Key Mistakes and Corrections → Architectural Transitions → Engineering Lessons → Evidence Index → Limitations
- Refactor wave included in narrative LLM context as "Refactor Wave Detected" section

### Tests added

- `tests/unit/test_refactor_wave_detection.py` — 5 tests
- `tests/unit/test_narrative_service.py` — 3 new tests (refactor wave in prompt, spec 004 sections, category distribution in prompt)

### Production behavior added

- `domain/patterns.py` — `RefactorWave` frozen dataclass; `PatternReport.refactor_wave` field
- `application/pattern_detection_service.py` — `_compute_refactor_wave`, `refactor_wave_threshold` param on `detect()`
- `application/narrative_service.py` — spec 004 system prompt; refactor wave section in user message
- `interfaces/cli.py` — `_print_pattern_report` shows refactor wave

### Known limitation

Refactor wave is a global count, not temporal clustering. A true wave would require joining `commit_analyses` with `commit_facts.committed_at`. Tracked for future improvement.

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

## Batch 32 — Temporal narrative ordering and test growth signal

### Goal

Make the narrative engine present commits in chronological order (oldest → newest) and add a test growth signal pattern detector.

### Source of truth

- `specs/003-pattern-detection.md`
- `specs/004-narrative-engine.md`

### Examples covered

- Narrative now orders commits by `committed_at ASC` using a JOIN between `commit_analyses` and `commit_facts`
- Test growth signal: ratio of test commits to bugfix commits as a quality health indicator
- `TimestampedAnalysis` DTO carries `committed_at` alongside `CommitAnalysis`

### Tests added

- `tests/unit/test_sqlite_commit_analysis_store.py` — `list_analyses_with_dates` tests
- `tests/unit/test_narrative_service.py` — temporal ordering tests
- `tests/unit/test_test_growth_signal.py` — test growth signal detection tests

### Production behavior added

- `application/ports.py` — `TimestampedAnalysis`, `TemporalAnalysisReader` Protocol
- `infrastructure/sqlite.py` — `SqliteCommitAnalysisStore.list_analyses_with_dates()` with JOIN on `commit_facts`
- `domain/patterns.py` — `TestGrowthSignal` frozen dataclass; `PatternReport.test_growth_signal`
- `application/pattern_detection_service.py` — `_compute_test_growth_signal`
- `application/narrative_service.py` — uses `TemporalAnalysisReader` for chronological ordering
- `interfaces/cli.py` — `_print_pattern_report` shows test growth signal

## Batch 33 — Ownership concentration pattern detection

### Goal

Detect knowledge silos: files touched by very few authors relative to their commit count.

### Source of truth

- `specs/003-pattern-detection.md`

### Examples covered

- File with 20 commits but only 1 author → ownership concentration (knowledge silo risk)
- Configurable `ownership_threshold` (default: author_count ≤ 2)
- JOIN between `file_facts` and `commit_facts` to count distinct authors per file

### Tests added

- `tests/unit/test_ownership_concentration.py` — 7 tests
- `tests/unit/test_sqlite_ownership_reader.py` — 4 tests

### Production behavior added

- `application/ports.py` — `FileOwnershipRecord`, `OwnershipReader` Protocol
- `domain/patterns.py` — `OwnershipConcentration` frozen dataclass; `PatternReport.ownership_concentrations`
- `application/pattern_detection_service.py` — optional `ownership_reader`; `_compute_ownership_concentrations`
- `infrastructure/sqlite.py` — `SqliteFileFactReader.get_file_ownership()` with JOIN query
- `composition.py` — wires `SqliteFileFactReader` as `ownership_reader`
- `interfaces/cli.py` — `_print_pattern_report` shows ownership concentrations

## Batch 34 — Revert signal pattern detection

### Goal

Detect instability via revert commit ratio as a signal of rework or broken workflows.

### Source of truth

- `specs/003-pattern-detection.md`

### Examples covered

- Commit messages starting with `"revert"` (case-insensitive) counted
- `revert_ratio = revert_count / total_commit_count`
- Configurable `revert_threshold` (default: ratio ≥ 0.05)
- Uses `CommitSummaryRecord` reader to scan all commit messages without loading full analyses

### Tests added

- `tests/unit/test_revert_signal_detection.py` — 8 tests
- `tests/unit/test_sqlite_commit_summary_reader.py` — 4 tests

### Production behavior added

- `application/ports.py` — `CommitSummaryRecord`, `CommitSummaryReader` Protocol
- `domain/patterns.py` — `RevertSignal` frozen dataclass; `PatternReport.revert_signal`
- `application/pattern_detection_service.py` — optional `commit_summary_reader`; `_compute_revert_signal`
- `infrastructure/sqlite.py` — `SqliteCommitReader.list_commit_messages()`
- `composition.py` — wires `SqliteCommitReader` as `commit_summary_reader`
- `interfaces/cli.py` — `_print_pattern_report` shows revert signal

## Batch 35 — Case study persistence and cache

### Goal

Cache generated case studies in SQLite so repeated `case-study` calls skip the LLM.

### Source of truth

- `specs/004-narrative-engine.md`

### Examples covered

- First call generates and stores; second call returns cached without LLM
- `--force` flag bypasses cache and regenerates
- `CaseStudyRecord` fields: `repository_id`, `narrative`, `commit_count`, `hotspot_count`
- UPSERT on conflict (not INSERT OR IGNORE) so regeneration overwrites stale data

### Tests added

- `tests/unit/test_case_study_persistence.py` — 6 tests
- `tests/unit/test_sqlite_case_study_store.py` — 4 tests

### Production behavior added

- `application/ports.py` — `CaseStudyRecord`, `CaseStudyStore` Protocol
- `infrastructure/sqlite.py` — `SqliteCaseStudyStore` with `case_studies` table; UPSERT on conflict
- `application/narrative_service.py` — optional `case_study_store`; cache check before LLM call; `force: bool = False` param on `generate()`
- `composition.py` — `build_narrative_service` wires `SqliteCaseStudyStore`
- `interfaces/cli.py` — `case-study` gains `--force` flag; `NarrativeGeneratorService` Protocol updated

## Batch 36 — Pipeline run command

### Goal

Add `git-it run <url>` to execute the full pipeline (ingest → analyze-commits → case-study) in a single command.

### Source of truth

- MVP usability requirement

### Examples covered

```text
$ git-it run https://github.com/owner/repo
Ingesting...
Ingestion status: COMPLETED
Commits: 946 inserted, 0 reused
Files: 4368 inserted, 0 reused
Analyzing commits...
Analyzed 10 commits.
Generating case study...
Case Study (10 commits, 3 hotspot files)
...
```

With flags: `--model`, `--limit`, `--force`

### Tests added

- `tests/unit/test_pipeline_run_command.py` — 15 tests covering happy path, step invocation, progress output, limit/force/model forwarding, ingestion failure abort

### Production behavior added

- `interfaces/cli.py` — `run` subparser with `--model`, `--limit`, `--force`; `_run_pipeline` orchestrates the three steps; aborts with exit 1 if ingestion fails

## Bug fix — commit SHA truncation breaking JOIN queries

### Problem

`CommitAnalysisService._build_messages()` sends `commit.sha[:12]` to the LLM. The LLM echoes the 12-char SHA back as `CommitAnalysis.commit_sha`. When stored, `commit_analyses.commit_sha` is 12 chars while `commit_facts.sha` is 40 chars. The `list_analyses_with_dates()` JOIN returns zero rows → "No analyses found" on `case-study`.

### Fix

After the LLM call, override with the authoritative full SHA from the commit record:

```python
analysis = self.analyze_commit(commit)
analysis = analysis.model_copy(update={"commit_sha": commit.sha})
```

### Regression test added

`tests/unit/test_commit_analysis_service.py` — `test_analyze_commits_stores_full_sha_not_llm_sha`

### Commit

`8018a1e fix: override commit_sha with full sha after llm analysis`

## Batch 37 — Commit pre-classifier (skip/include/sample)

### Goal

Classify commits before any LLM call to eliminate noise and guarantee high-signal commits are always analyzed.

### Source of truth

- Cost optimization strategy: eliminate automated/bot commits from LLM budget

### Examples covered

- Skip: Dependabot bumps, merge commits, lock file updates, format-only, CI automation, Snyk, Renovate, release/changelog
- Include: `feat:/fix:/refactor:/perf:` conventional commits, breaking changes (`!` scope, `BREAKING CHANGE`), security/auth/migration keywords, reverts
- Sample: everything else (default LLM flow)
- Gotcha: `"fix: typo"` must NOT be `include` — typo check on first 20 chars of first line

### Tests added

- `tests/unit/test_commit_pre_classifier.py` — 31 tests
- `tests/unit/test_commit_analysis_service.py` — 4 wiring tests

### Production behavior added

- `application/pre_classifier.py` — `CommitPreClassification` dataclass, `CommitPreClassifier` (stateless, pure functions)
- `application/commit_analysis_service.py` — classifier called after cache check; `skip` → `continue` (no LLM, absent from results)

### Commits

- `da0b4b3 feat: add commit pre-classifier with skip and include rules`
- `9613f66 feat: wire pre-classifier into commit analysis service`

## Batch 38 — Budget guardrail with `--yes` flag

### Goal

Show how many LLM calls will be made before running, and ask for confirmation when above a threshold.

### Source of truth

- Cost safety: prevent accidental large LLM runs

### Examples covered

```text
$ git-it run https://github.com/owner/repo
  143 commits will be sent to LLM.
143 LLM calls planned. Proceed? [y/N]
```

```text
$ git-it run https://github.com/owner/repo --yes   # skips confirmation
```

### Tests added

- `tests/unit/test_commit_analysis_estimate.py` — 8 tests
- `tests/unit/test_analyze_commits_cli.py` — 4 budget tests
- `tests/unit/test_pipeline_run_command.py` — 4 budget tests

### Production behavior added

- `application/commit_analysis_service.py` — `estimate_llm_calls(repository_id, *, limit)` method
- `interfaces/cli.py` — `CommitBatchService` Protocol gains `estimate_llm_calls`; `--yes` flag on `analyze-commits` and `run`; `budget_confirm_fn` and `budget_threshold` injectable params on `main()` (default threshold: 50)

### Gotchas

- mypy rejects `lambda n: (list.append(n), False)[1]` — use `def` instead
- `FakeCacheReader` must implement `list_analyses()` even if unused to satisfy Protocol structurally

### Commits

- `4fcb49e feat: add estimate_llm_calls to commit analysis service`
- `6ff3da6 feat: add budget guardrail with --yes flag`

## Batch 39 — Repo profile injection

### Goal

Inject the existing case study narrative as background context into the system prompt for each commit analysis, so the LLM categorizes commits knowing the project's domain without re-analyzing everything.

### Source of truth

- Quality improvement: context-aware commit categorization

### Examples covered

- First run (no case study): no context injected
- Second run (case study exists): first 2000 chars of narrative injected as `## Repository Background` in system prompt
- Context fetched once per `analyze_commits()` batch, passed to every LLM call

### Tests added

- `tests/unit/test_commit_analysis_repo_context.py` — 9 tests
- `tests/unit/test_sqlite_case_study_store.py` — 2 new tests

### Production behavior added

- `application/ports.py` — `RepoContextReader` Protocol
- `infrastructure/sqlite.py` — `SqliteCaseStudyStore.get_repo_context()` returns `narrative[:2000]`; constant `_REPO_CONTEXT_MAX_CHARS = 2000`
- `application/commit_analysis_service.py` — `repo_context_reader` param; `_build_messages` gains `repo_context` kwarg; sentinel pattern to avoid double reader call
- `composition.py` — `build_commit_analysis_service` wires `SqliteCaseStudyStore` as `repo_context_reader`

### Gotcha

Sentinel pattern (`_SENTINEL = object()`) in `analyze_commit()` distinguishes "no context passed" (consult reader) from "explicit `None`" (skip reader), preventing double fetch when `analyze_commits()` pre-fetches.

### Commits

- `09baa09 feat: add RepoContextReader port and get_repo_context to SqliteCaseStudyStore`
- `830c49c feat: inject repo context into commit analysis system prompt`

## Batch 40 — Chronological ordering and date filters

### Goal

Allow users to analyze commits from oldest to newest (`--order oldest`) and filter by date range (`--since`, `--until`).

### Source of truth

- UX improvement: "follow the repo from day 1"

### Examples covered

```text
$ git-it run https://github.com/owner/repo --order oldest --limit 20
$ git-it analyze-commits https://github.com/owner/repo --since 2024-01-01 --until 2024-06-30
$ git-it commits https://github.com/owner/repo --order oldest
```

### Tests added

- `tests/unit/test_sqlite_commit_reader_ordering.py` — 10 tests
- `tests/unit/test_commit_analysis_ordering.py` — 6 tests
- New ordering/date tests in CLI test files

### Production behavior added

- `application/commit_query_service.py` — `CommitReader` Protocol and `RepositoryCommitQueryService` extended with `order: str = "newest"`, `since: str | None = None`, `until: str | None = None`
- `infrastructure/sqlite.py` — conditional `WHERE substr(committed_at, 1, 10) >= ?` / `<= ?` and dynamic `ORDER BY committed_at ASC/DESC`
- `application/commit_analysis_service.py` — `analyze_commits` and `estimate_llm_calls` forward the new params
- `interfaces/cli.py` — `--order`, `--since`, `--until` on `commits`, `analyze-commits`, `run`; Protocol updates

### Gotcha

Use `str` (not `Literal["newest", "oldest"]`) in Protocol method signatures. mypy enforces parameter contravariance — a narrower Literal type on the concrete class causes Protocol violations.

### Commits

- `458d7b0 feat: add order, since, until to commit reader and sqlite`
- `ff67273 feat: wire order, since, until through service and cli`

---

## Batch 41 — Tiered model routing

### Goal

Route commit analysis to different LLM models based on the pre-classifier tier: `include`-tier commits (feat/fix/refactor/breaking/security) go to the primary (premium) model; `sample`-tier commits (everything else that isn't skipped) go to a cheaper/faster model. This allows users to configure e.g. `--model anthropic/claude-sonnet-4-6 --sample-model anthropic/claude-haiku-4-5-20251001`.

### Source of truth

Pre-classifier tier decisions from Batch 37 (`CommitPreClassifier`). LiteLLM model string convention already established.

### Examples covered

```text
$ git-it run https://github.com/owner/repo \
    --model anthropic/claude-sonnet-4-6 \
    --sample-model anthropic/claude-haiku-4-5-20251001

$ git-it analyze-commits https://github.com/owner/repo \
    --sample-model ollama/llama3.2
```

### Tests added

- `tests/unit/test_commit_analysis_tiered_models.py` — 6 tests (routing logic: include→primary, sample→sample_client, fallback when no sample_client, public `analyze_commit()` always uses primary, mixed batch, skip goes to neither)
- New `--sample-model` CLI tests in `test_analyze_commits_cli.py` and `test_pipeline_run_command.py`

### Production behavior added

- `application/commit_analysis_service.py` — `sample_client: CommitAnalysisClient | None = None` constructor param; `_analyze_with_client(client, commit, *, repo_context)` private method; `analyze_commits()` selects `sample_client` when tier is `"sample"` and sample_client is configured
- `composition.py` — `build_commit_analysis_service()` gains `sample_model: str | None = None`; creates `InstructorCommitAnalysisAdapter(model=sample_model)` only when `sample_model` differs from `model`
- `interfaces/cli.py` — `CommitAnalysisFactory` Protocol updated; `--sample-model` added to `analyze-commits` and `run`; forwarded through `_run_analyze_commits` and `_run_pipeline`

### Design note

When `sample_model == model` (or omitted), `sample_client` is `None` — the service falls through to `self._client` for both tiers. No wasted adapter instance. The public `analyze_commit()` single-commit method always uses the primary client — tiered routing only applies inside the `analyze_commits()` batch loop.

### Commits

- `29ff240 feat: add sample_client to commit analysis service for tiered model routing`
- `b4556db feat: add --sample-model flag and wire tiered model routing`

---

## Batch 42 — Incremental case study update

### Goal

When a case study already exists for a repository, regenerate it using only the *new* commit analyses (those added after the case study was last generated) combined with the existing narrative as context. If there are no new analyses, return the existing case study without any LLM call.

### Source of truth

Both `commit_analyses` and `case_studies` tables already had `created_at` columns — timestamp-based approach (Option A) required no schema migration.

### Examples covered

```text
# First run — no existing case study — all 47 analyses sent to LLM
$ git-it run https://github.com/owner/repo

# Second run — 3 new commits since last run — only 3 analyses + existing narrative sent
$ git-it run https://github.com/owner/repo

# Third run — no new commits — LLM skipped entirely, existing case study returned
$ git-it run https://github.com/owner/repo
```

### Tests added

- `tests/unit/test_case_study_incremental.py` — 15 new TDD tests covering: full generation (no existing), incremental delta (new analyses only), skip LLM (no new analyses), prompt structure verification for both paths

### Production behavior added

- `application/ports.py` — `CaseStudyRecord` gains `generated_at: str | None = None`; new `TemporalAnalysisReader` Protocol with `list_analyses_since(repository_id, *, since: str)`
- `infrastructure/sqlite.py` — `SqliteCommitAnalysisStore.list_analyses_since()` filters by `created_at > since`; `SqliteCaseStudyStore.get_case_study()` returns `created_at` as `generated_at`
- `application/narrative_service.py` — `generate()` refactored into `_generate_full()` + `_generate_incremental()`; incremental path uses `_INCREMENTAL_SYSTEM_PROMPT` + "Existing Case Study" + "New Commits to Incorporate" sections in user message

### Gotcha

Legacy `CaseStudyRecord` instances without `generated_at` (value `None`) cause `_resolve_new_analyses()` to return `[]`, which correctly falls through to the existing cached record — backward-compatible behaviour for records written before this batch.

### Commits

- `eb230c3 feat: add incremental analysis query support`
- `f12c3f4 feat: implement incremental case study update`

---

## Batch 43 — Parallel async analysis

### Goal

Run multiple LLM calls concurrently instead of sequentially. A new `--concurrency N` flag controls the maximum number of parallel calls. Default is 1 (sequential, same behaviour as before).

### Design

`asyncio.to_thread()` wraps each sync `_analyze_with_client()` call so it runs in the thread pool without changing any Protocol. `asyncio.Semaphore(concurrency)` bounds parallelism. `asyncio.gather()` collects results. The original commit order is reconstructed after gathering by iterating the original `commits` list and looking up cached/analyzed SHAs in maps.

### Examples covered

```text
# Sequential (default)
$ git-it run https://github.com/owner/repo --concurrency 1

# 5 parallel LLM calls
$ git-it analyze-commits https://github.com/owner/repo --concurrency 5
```

### Tests added

- `tests/unit/test_commit_analysis_async.py` — 9 async service tests (same results as sync, concurrency limit enforced via `ConcurrencyTrackingClient`, order preserved, cached/skip bypass, sample routing)
- New `--concurrency` CLI tests in `test_analyze_commits_cli.py` and `test_pipeline_run_command.py`

### Production behavior added

- `application/commit_analysis_service.py` — new `analyze_commits_async()` method (existing sync `analyze_commits()` untouched)
- `interfaces/cli.py` — `CommitBatchService` Protocol gains `async def analyze_commits_async()`; `--concurrency` on `analyze-commits` and `run`; when `N > 1` routes through `asyncio.run(service.analyze_commits_async(...))`

### Gotchas

- `asyncio.to_thread()` returns `Any` — requires explicit type annotation on the awaited result (`analysis: CommitAnalysis = await asyncio.to_thread(...)`)
- `asyncio_mode = auto` in `pytest.ini` means `async def test_...` works without decorators
- `FakeAnalysisCache` must implement the full `CommitAnalysisReader` Protocol (including `list_analyses()`) even if unused in a specific test

### Commits

- `d354915 feat: add analyze_commits_async with semaphore-based concurrency`
- `92a40fb feat: add --concurrency flag to cli`

---

## Batch 44 — Pattern enrichment with evidence, time range, and confidence

### Goal

Enrich every detected pattern with three new fields required by spec 003: evidence commit SHAs (which commits triggered the pattern), time range (earliest/latest committed_at among evidence commits), and a deterministic confidence score.

### Examples covered

```text
Hotspots (files with ≥5 commits):
  src/auth.py: 42 commits, churn 8,234  [confidence: 1.00]
    Evidence: a1b2c3d, e4f5g6h, ...
    Period: 2024-01-15 → 2026-06-01
```

### Tests added

- `tests/unit/test_pattern_enrichment.py` — 10 new tests (confidence formulas, evidence SHAs, time_range derivation, defaults when readers absent)
- `tests/unit/test_sqlite_file_evidence.py` — 3 SQLite integration tests (top-N evidence commits, limit param, date map)
- New tests added to `test_pattern_detection_service.py`

### Production behavior added

- `domain/patterns.py` — all 6 pattern dataclasses gain `evidence_commit_shas: tuple[str, ...] = ()`, `time_range: tuple[str, str] | None = None`, `confidence: float = 0.0`
- `infrastructure/sqlite.py` — `SqliteCommitReader.get_commit_date_map()` returns `{sha: committed_at}`; `SqliteFileFactReader.get_file_evidence_commits()` returns top-N most-recent SHAs per file
- `application/ports.py` — `CommitDateReader` and `FileEvidenceReader` protocols added
- `application/pattern_detection_service.py` — two new optional constructor params; `detect()` pre-fetches both maps; each sub-detector computes evidence + time_range + confidence
- `interfaces/cli.py` — `_print_pattern_report` shows confidence %, 7-char abbreviated SHAs, and period
- `composition.py` — wired new readers

### Confidence formulas

| Pattern | Formula |
|---|---|
| Hotspot | `min(1.0, commit_count / 20)` |
| BugfixRecurrence | `min(1.0, bugfix_commit_count / 10)` |
| RefactorWave | `min(1.0, refactor_ratio * 2.0)` |
| TestGrowthSignal | `min(1.0, test_to_bugfix_ratio / 2.0)` |
| RevertSignal | `min(1.0, revert_ratio * 5.0)` |
| OwnershipConcentration | `1.0 - min(1.0, (author_count - 1) / 5.0)` |

### Commits

- `b97091c feat: add evidence, time_range, confidence fields to pattern domain models`
- `dab5064 feat: add file evidence and commit date readers to sqlite infrastructure`
- `9092f27 feat: wire evidence enrichment into pattern detection service`

---

## Batch 45 — LLM pattern synthesis

### Goal

Add an LLM synthesis layer to pattern detection. After all rule-based detectors run, pass the `PatternReport` to an LLM that produces a brief educational explanation per detected pattern — "why it matters" and "what engineers can learn from it". The LLM is never the sole source of evidence; it only explains patterns already proven by rule-based detection.

### Examples covered

```text
$ git-it patterns https://github.com/owner/repo --model anthropic/claude-haiku-4-5-20251001

Hotspots ...
...

Educational Insights
====================
[HOTSPOT] src/auth.py
  Why it matters: High churn in authentication code correlates with repeated security fixes...
  Takeaway: Consider extracting the authentication module into a separate, well-tested service.
```

### Tests added

- `tests/unit/test_pattern_synthesis.py` — 9 new tests (synthesis called/skipped, explanations attached, user message structure, `_report_has_patterns` utility)
- New `--model` flag tests in `test_patterns_cli.py`

### Production behavior added

- `domain/patterns.py` — `PatternExplanation` frozen dataclass (`pattern_type`, `pattern_key`, `why_it_matters`, `engineer_takeaway`, `confidence_note`); `PatternReport` gains `explanations: list[PatternExplanation]`
- `application/ports.py` — `PatternSynthesisClient` Protocol added
- `infrastructure/llm.py` — `InstructorPatternSynthesisAdapter` with `_PATTERN_SYNTHESIS_SYSTEM_PROMPT` (security note for untrusted Git data) and `_build_pattern_synthesis_user_message()` helper
- `application/pattern_detection_service.py` — `synthesis_client` optional param; `_report_has_patterns()` guard; `dataclasses.replace()` attaches explanations
- `composition.py` — `build_pattern_detection_service()` gains `model: str | None`; wires adapter when provided
- `interfaces/cli.py` — `patterns` command gains `--model`; `PatternFactory` Protocol updated; `_print_pattern_report` renders "Educational Insights" section

### Gotcha

`PatternFactory` Protocol signature change required updating the inner `_factory()` helper in the existing CLI test — needed `model: str | None` param.

### Commits

- `904b468 feat: add PatternExplanation domain model and PatternSynthesisClient port`
- `ecbfa52 feat: wire LLM pattern synthesis into pattern detection service and cli`

---

## Batch 46 — Dependency migration and architectural shift detectors

### Goal

Add two new rule-based pattern detectors from spec 003 that were previously unimplemented: dependency migrations (library replacements detected from commit messages) and architectural shifts (top-level directory structure analysis).

### Examples covered

```text
Dependency Migrations:
  requests → httpx: 2 commits  [confidence: 67%]
    Evidence: a1b2c3d, e4f5g6h
    Period: 2024-03-01 → 2024-04-15

Architectural Shifts:
  [new_top_level_dir] Directory 'services/' contains 47 tracked files  [confidence: 1.00]
  [module_extraction] Multiple significant top-level modules detected  [confidence: 0.60]
```

### Tests added

- `tests/unit/test_dependency_migration_detector.py` — 10 tests (regex patterns, noise filtering, grouping, confidence, evidence SHAs)
- `tests/unit/test_architectural_shift_detector.py` — 6 tests (top-level dir threshold, single-dir skip, module extraction signal)
- 2 integration tests in `test_pattern_detection_service.py`

### Production behavior added

- `domain/patterns.py` — `DependencyMigration` and `ArchitecturalShift` frozen dataclasses; `PatternReport` gains `dependency_migrations` and `architectural_shifts` fields
- `application/pattern_detection_service.py` — `_compute_dependency_migrations()` (5 regex patterns: migrate/replace/switch/move from X to Y; noise filtering for short tokens and common words; confidence `min(1.0, count/3.0)`); `_compute_architectural_shifts()` (top-level dir file counts; module extraction signal when ≥3 dirs have ≥5 files each; skip when only 1 top-level dir); both wired into `detect()`; `_report_has_patterns()` updated
- `interfaces/cli.py` — two new output sections in `_print_pattern_report`

### Gotcha

The architectural shift detector skips output when only 1 top-level directory exists (no multi-module signal). Tests that exercise the "new top-level dir" path need at least 2 distinct top-level dirs in the file churn data.

### Commits

- `6b5a3c7 feat: add DependencyMigration and ArchitecturalShift domain models`
- `9b51968 feat: implement dependency migration and architectural shift detectors`
