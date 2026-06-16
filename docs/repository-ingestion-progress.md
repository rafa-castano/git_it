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
