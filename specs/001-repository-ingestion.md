# Spec 001: Repository Ingestion

Status: Accepted  
Owner: TBD  
Primary agent: Software Engineering Agent  
Supporting agents: Architecture Agent, Security Agent, Quality Agent

## 1. Summary

The system accepts a public GitHub repository URL, validates it, retrieves repository metadata, clones or fetches its Git history into a controlled workspace, extracts commits and file changes, and stores raw facts for later analysis.

The MVP uses a local-first ingestion path: public `github.com` repositories, safe bare clone/fetch, no repository code execution, and SQLite-backed fact persistence behind a storage port.

## 2. Problem

Commit and pattern analysis require reliable raw repository facts. The system must ingest public repositories safely without executing untrusted code.

## 3. Goals

- Accept valid public GitHub repository URLs.
- Reject invalid or unsupported URLs.
- Provide a local CLI entrypoint backed by an application service.
- Provide stable application/query service DTOs for future adapters.
- Retrieve repository metadata.
- Extract default-branch commit history by default.
- Optionally extract all public remote branch histories when explicitly requested.
- Extract file-level changes.
- Store branch/ref membership separately from unique commit facts.
- Store raw facts separately from AI interpretations.
- Avoid executing repository code.

## 4. Non-goals

- Private repository support.
- GitHub Enterprise support.
- SSH, `git://`, `file://`, or arbitrary Git remote support.
- Running tests from the target repository.
- Working tree checkout for analyzed repositories.
- Submodule initialization.
- Git LFS blob fetching.
- GitHub Release mining, release asset downloads, and changelog parsing for the MVP ingestion path.
- Full issue/PR analysis.
- FastAPI endpoint for repository ingestion in the first MVP phase.
- Background worker orchestration for repository ingestion in the first MVP phase.
- GUI-specific read models in the first MVP phase.
- Pattern detection.
- Narrative generation.

## 5. MVP URL contract

Accepted input formats:

```text
https://github.com/{owner}/{repo}
https://github.com/{owner}/{repo}.git
```

Normalization rules:

```text
https://github.com/{owner}/{repo}.git
→ owner = {owner}
→ repo = {repo}
→ canonical_url = https://github.com/{owner}/{repo}
```

Rejected input formats:

```text
http://github.com/...
git@github.com:owner/repo.git
ssh://git@github.com/owner/repo.git
git://github.com/owner/repo.git
file://...
https://github.com/{owner}
https://github.com/{owner}/{repo}/tree/{branch}
https://github.com/{owner}/{repo}/pull/{id}
https://github.enterprise.local/...
```

URL parsing is a security boundary. The MVP must not pass arbitrary user-provided Git remotes directly to Git tooling.

## 6. User stories

```md
As a learner,
I want to submit a public GitHub repository,
so that I can later explore how it evolved.
```

```md
As a local contributor,
I want to run repository ingestion from the command line,
so that I can test the MVP without starting servers, workers, containers, or cloud services.
```

```md
As a maintainer,
I want ingestion to store raw facts separately from AI analysis,
so that later interpretations are auditable.
```

## 7. Acceptance criteria

```gherkin
Given a local development checkout
When a contributor runs git-it ingest https://github.com/owner/repo
Then ingestion runs through the application service
And does not require FastAPI, workers, containers, or cloud services.
```

```gherkin
Given a local development checkout
When a contributor runs git-it ingest https://github.com/owner/repo --include-all-branches
Then ingestion runs with include_all_branches set to true.
```

```gherkin
Given a completed ingestion run
When the CLI finishes without --json
Then it prints a human-readable summary including repository, canonical URL, run ID, status, inserted/reused counts, branch count, tag count, and limitations.
```

```gherkin
Given a completed ingestion run
When the CLI finishes with --json
Then it prints a stable JSON object including run_id, status, repository, counts, and limitations.
```

```gherkin
Given a failed ingestion run
When the CLI finishes
Then it returns a non-zero exit code
And prints a safe error summary without secrets, raw emails, stack traces, or credential-bearing URLs.
```

```gherkin
Given ingestion fails
When the failure is recorded
Then the system stores a machine-readable error code, stage, retryable flag, and safe error message.
```

```gherkin
Given ingestion succeeds with degraded metadata
When the run completes
Then the system records the limitation without marking the run as failed.
```

```gherkin
Given a completed ingestion run
When an adapter asks for the ingestion run summary through the query service
Then the service returns a stable DTO with run ID, repository summary, status, counts, timestamps, and limitations.
```

```gherkin
Given an ingested repository
When an adapter asks for repository overview through the query service
Then the service returns a stable DTO with repository metadata, default branch, branch count, tag count, commit count, and latest ingestion status.
```

```gherkin
Given an ingested repository
When an adapter asks for branch and tag lists through the query service
Then the service returns stable DTOs without exposing storage-specific models.
```

```gherkin
Given an ingested repository
When an adapter asks for a commit list page through the query service
Then the service returns a paginated stable DTO with commit facts, contributor identity confidence, refs/tags, and limitations.
```

```gherkin
Given an ingested commit
When an adapter asks for file changes through the query service
Then the service returns a stable DTO with file-change metadata, diff truncation status, binary status, and limitations.
```

```gherkin
Given the URL https://github.com/owner/repo
When ingestion validates the URL
Then the URL is accepted
And the canonical URL is https://github.com/owner/repo.
```

```gherkin
Given the URL https://github.com/owner/repo.git
When ingestion validates the URL
Then the URL is accepted
And the canonical URL is https://github.com/owner/repo.
```

```gherkin
Given a valid public GitHub repository URL
When ingestion starts
Then the system stores repository metadata, commits, file changes, and branch/ref membership for the default branch.
```

```gherkin
Given a valid public GitHub repository URL
And GitHub metadata is temporarily unavailable
And the repository can still be cloned or fetched
When ingestion runs
Then ingestion continues with degraded metadata
And records a limitation describing the metadata gap.
```

```gherkin
Given a valid public GitHub repository URL
And GitHub metadata confirms the repository is missing, private, or inaccessible
When ingestion runs
Then ingestion fails safely with FAILED_FETCH.
```

```gherkin
Given a valid public GitHub repository URL
And the ingestion option include_all_branches is true
When ingestion starts
Then the system stores unique commits by SHA
And stores which remote branches reference each commit without duplicating commit facts.
```

```gherkin
Given a previously observed branch disappears from the remote
When the repository is re-ingested
Then the system marks the branch ref as missing on remote
And preserves previously observed commits and memberships as historical facts.
```

```gherkin
Given a previously observed branch is force-pushed to a different head
When the repository is re-ingested
Then the system updates the branch ref to the latest observed head
And preserves previously observed commits
And records the ref movement as repository history evidence.
```

```gherkin
Given a repository with Git tags
When ingestion runs
Then the system stores tag ref metadata
And does not treat tags as proof of release quality, deployment, or operational events.
```

```gherkin
Given an invalid URL
When ingestion starts
Then the system rejects the URL with a safe validation error.
```

```gherkin
Given a URL using HTTP, SSH, git protocol, file protocol, GitHub Enterprise, owner-only paths, tree paths, or pull-request paths
When ingestion validates the URL
Then the system rejects the URL before invoking Git tooling.
```

```gherkin
Given a repository containing executable code
When ingestion runs
Then the system must not execute repository code.
```

```gherkin
Given a repository with submodules or Git LFS pointers
When ingestion runs with default MVP options
Then the system must not initialize submodules
And must not fetch Git LFS blobs.
```

```gherkin
Given an ingestion input that exceeds configured limits
When ingestion runs
Then the system stops safely
And records the ingestion status as LIMIT_EXCEEDED.
```

```gherkin
Given an ingestion run that has not reached COMPLETED
When downstream analysis requests repository facts
Then those facts are not considered queryable for analysis.
```

```gherkin
Given a commit with multiple changed files
When ingestion extracts the commit
Then each file change is stored with path, change type, additions, deletions, and diff summary metadata when available.
```

```gherkin
Given a file change with a textual diff larger than the stored diff limit
When ingestion extracts the file change
Then the system stores a truncated diff preview
And records that the diff was truncated.
```

```gherkin
Given a file change for a binary file
When ingestion extracts the file change
Then the system stores file-change metadata
And does not store binary file content.
```

```gherkin
Given a stored file change with a truncated diff
And the user explicitly asks for the full diff
And the bare clone cache exists
When the system retrieves the full diff
Then the system reconstructs the full diff from the bare clone cache without checking out a working tree.
```

```gherkin
Given a stored file change with a truncated diff
And the user explicitly asks for the full diff
And the bare clone cache is missing
When the system retrieves the full diff
Then the system attempts a safe bare cache refresh from the canonical repository URL
And applies the same URL, timeout, workspace, submodule, and Git LFS restrictions as ingestion.
```

```gherkin
Given a full diff cannot be safely reconstructed or refreshed
When the user asks for the full diff
Then the system returns the stored truncated diff
And includes a limitation explaining that the full diff is unavailable.
```

```gherkin
Given GitHub provides commit signature verification metadata
When ingestion stores the commit fact
Then the system stores signature verification metadata as provenance evidence
And does not treat it as proof of developer intent.
```

## 8. Evidence requirements

Raw facts must include:

- repository URL,
- normalized repository URL,
- repository owner/name,
- commit SHA,
- author and committer identity metadata according to the contributor identity rules,
- commit signature verification metadata when available,
- committed timestamp,
- commit message,
- parent SHAs,
- file paths,
- additions/deletions,
- change type.

Contributor identity facts must include:

- GitHub user ID or node ID when GitHub associates the commit with an account,
- GitHub login as an observed label when available,
- Git author name,
- Git committer name,
- contributor email key only when generated through the approved HMAC fallback,
- identity source,
- identity confidence.

Contributor identity confidence levels:

```text
HIGH    = GitHub user ID or node ID is available.
MEDIUM  = HMAC-SHA256 email key is available but no GitHub account association exists.
LOW     = only Git author or committer name is available.
UNKNOWN = no reliable identity signal is available.
```

Raw email addresses must not be stored by default.

GitHub login must not be treated as a durable identity key because GitHub usernames can change and old usernames can be reclaimed.

Git author and committer names must not be treated as GitHub usernames. They are weak aliases only.

When GitHub account association is unavailable and identity confidence would otherwise be reduced, the system may generate `contributor_email_key` as:

```text
HMAC-SHA256(GIT_IT_IDENTITY_PEPPER, normalized_email)
```

Email normalization:

```text
trim whitespace
lowercase
```

Rules for email keys:

- use `GIT_IT_IDENTITY_PEPPER` as a secret pepper,
- do not store the raw email,
- do not log the raw email,
- do not store the pepper in the repository,
- do not use bcrypt or Argon2 for contributor correlation,
- outside deterministic tests/fixtures, do not generate email keys when the pepper is missing,
- when the pepper is missing, lower identity confidence and record a limitation,
- tests may use a deterministic test pepper.

Commit signature verification facts may include:

- signature verified flag,
- signature verification reason,
- verified timestamp when available.

Signature verification is provenance evidence. It must not be treated as proof of developer intent or absolute authorship.

File-change diff facts must include:

- old path,
- new path,
- change type,
- additions,
- deletions,
- textual diff preview when available,
- diff byte count stored,
- diff truncated flag,
- binary file flag,
- generated/vendor guess flag when available,
- language guess when available.

The generated/vendor flag is heuristic. It must not be treated as a raw fact.

MVP repository metadata must include:

- owner,
- repo,
- canonical URL,
- default branch,
- fork status when available,
- archived status when available,
- visibility as `public`,
- pushed timestamp when available,
- fetched timestamp.

GitHub API or GitHub MCP is the preferred source for repository metadata.

If metadata fetch is temporarily unavailable but clone/fetch succeeds, ingestion may continue with degraded metadata and must record a limitation.

If metadata confirms the repository is missing, private, or inaccessible, ingestion must fail with `FAILED_FETCH`.

Local Git metadata may be used as fallback evidence for default branch detection only when GitHub metadata is temporarily unavailable.

Branch/ref facts must include:

- remote name,
- branch/ref name,
- referenced commit SHA,
- latest observed head SHA,
- whether the ref is the default branch,
- first seen timestamp,
- last seen timestamp,
- last checked timestamp,
- whether the ref is currently missing on remote.

Tag facts must include:

- tag name,
- target commit SHA,
- tag type as lightweight or annotated when detectable,
- tagger name when available,
- tag date when available,
- tag message preview when available.

Tags are repository markers that may help divide history into chapters. They must not automatically imply release quality, production deployment, or operational impact.

Ingestion run facts must include:

- ingestion run identifier,
- normalized repository URL,
- selected ingestion options,
- status,
- started/completed timestamps where available,
- error code and safe error message where applicable,
- error stage where applicable,
- retryable flag where applicable,
- limitations recorded during degraded ingestion,
- extracted repository, branch, commit, and file-change counts.

## 9. MVP data model

The MVP ingestion store uses these conceptual entities:

```text
Repository
IngestionRun
CommitFact
FileChangeFact
BranchRef
CommitBranchMembership
```

Uniqueness rules:

```text
Repository: unique canonical_url
CommitFact: unique repository_id + commit_sha
FileChangeFact: unique commit_id + old_path + new_path + change_type
BranchRef: unique repository_id + remote_name + ref_name
CommitBranchMembership: unique commit_id + branch_ref_id
IngestionRun: append-only per ingestion attempt
```

`IngestionRun` records an audit event. It must not replace previous runs.

Re-ingesting the same repository with the same options creates a new `IngestionRun`, reuses or upserts existing `Repository`, `CommitFact`, `FileChangeFact`, and `BranchRef` records, and records inserted vs reused counts.

`CommitFact` records are immutable once stored.

Facts must remain stable across ingestion runs unless the source repository has new reachable commits or refs.

Branch and ref state is observational:

- if a branch disappears from the remote, mark the `BranchRef` as missing on remote and update `last_checked_at`; do not delete historical facts,
- if a branch is force-pushed, update the latest observed head SHA and preserve previously observed commits,
- force-pushes and ref movements must be recorded as repository history evidence on the `IngestionRun`,
- downstream analysis must distinguish current remote state from previously observed history.

## 10. MVP ingestion options

MVP entrypoints:

```bash
git-it ingest https://github.com/owner/repo
git-it ingest https://github.com/owner/repo --include-all-branches
git-it ingest https://github.com/owner/repo --json
```

The CLI must call an application service. Domain logic must not live in the CLI adapter.

Default CLI output is human-readable:

```text
Ingestion completed
Repository: owner/repo
Canonical URL: https://github.com/owner/repo
Run ID: <ingestion_run_id>
Status: COMPLETED
Commits: <inserted> inserted, <reused> reused
File changes: <inserted> inserted, <reused> reused
Branches: <count>
Tags: <count>
Limitations: none
```

Machine-readable CLI output is available with `--json` and must use a stable schema:

```json
{
  "run_id": "<ingestion_run_id>",
  "status": "COMPLETED",
  "repository": {
    "owner": "owner",
    "repo": "repo",
    "canonical_url": "https://github.com/owner/repo"
  },
  "counts": {
    "commits_inserted": 0,
    "commits_reused": 0,
    "file_changes_inserted": 0,
    "file_changes_reused": 0,
    "branches": 0,
    "tags": 0
  },
  "limitations": []
}
```

Human-readable CLI output is not a stable integration contract. Tests and automation should use `--json`.

MVP query service DTOs:

```text
get_ingestion_run_summary(run_id)
get_repository_overview(repository_id)
list_repository_refs(repository_id)
list_commits(repository_id, page, page_size, filters)
list_commit_file_changes(commit_id)
get_ingestion_status(run_id)
```

These methods return stable DTOs for adapters. They must not expose SQLite rows, ORM models, PyDriller objects, GitHub API responses, or CLI-formatted text.

Minimum DTO coverage:

- ingestion run summary,
- repository overview,
- branch/tag list,
- paginated commit list,
- file changes for a commit,
- limitations and status.

`list_commits()` pagination and filtering:

```text
page: 1-based integer, default 1
page_size: default 50, maximum 200
sort: committed_at descending by default
```

Supported filters:

```text
branch_ref_id optional
tag_name optional
author_identity_id optional
path_prefix optional
since optional
until optional
```

Query services must reject invalid pagination values safely.

Default behavior:

- ingest the default branch only,
- ingest Git tag ref metadata,
- include merge commits,
- perform a bare clone/fetch,
- do not checkout a working tree,
- do not initialize submodules,
- do not fetch Git LFS blobs,
- persist facts to local SQLite through a storage port.

Supported option:

```yaml
include_all_branches: boolean
```

When `include_all_branches` is true, ingestion includes all public remote branches from origin up to the configured branch limit.

Commits must be stored uniquely by SHA. Branch/ref membership must be stored as a relationship, not by duplicating commit facts.

GitHub Releases, release assets, and changelog parsing remain outside the MVP ingestion path.

FastAPI and background worker entrypoints are intentionally outside the first MVP ingestion phase.

Future GUI services must consume application/query services or dedicated read models, not parse human-readable CLI output.

The MVP provides stable query DTOs to avoid blocking future GUI/API adapters, but does not introduce GUI-specific read models yet.

## 11. Ingestion lifecycle

An ingestion run uses these statuses:

```text
PENDING
VALIDATING_URL
FETCHING_METADATA
CLONING_OR_FETCHING
EXTRACTING_COMMITS
PERSISTING_FACTS
COMPLETED
FAILED_VALIDATION
FAILED_FETCH
FAILED_EXTRACTION
FAILED_PERSISTENCE
LIMIT_EXCEEDED
CANCELLED
```

Raw facts are queryable by downstream analysis only after the ingestion run reaches `COMPLETED`.

Failure/error model:

```text
INVALID_URL
UNSUPPORTED_URL
REPOSITORY_NOT_FOUND
REPOSITORY_PRIVATE_OR_INACCESSIBLE
METADATA_UNAVAILABLE
CLONE_TIMEOUT
INGESTION_TIMEOUT
LIMIT_EXCEEDED
GIT_FETCH_FAILED
EXTRACTION_FAILED
STORAGE_FAILED
CANCELLED_BY_USER
```

Default failure mapping:

| Terminal status | Error code | Stage | Retryable |
|---|---|---|---|
| `FAILED_VALIDATION` | `INVALID_URL` | `VALIDATING_URL` | false |
| `FAILED_VALIDATION` | `UNSUPPORTED_URL` | `VALIDATING_URL` | false |
| `FAILED_FETCH` | `REPOSITORY_NOT_FOUND` | `FETCHING_METADATA` | false |
| `FAILED_FETCH` | `REPOSITORY_PRIVATE_OR_INACCESSIBLE` | `FETCHING_METADATA` | false |
| `FAILED_FETCH` | `METADATA_UNAVAILABLE` | `FETCHING_METADATA` | true |
| `FAILED_FETCH` | `CLONE_TIMEOUT` | `CLONING_OR_FETCHING` | true |
| `FAILED_FETCH` | `GIT_FETCH_FAILED` | `CLONING_OR_FETCHING` | true |
| `FAILED_EXTRACTION` | `EXTRACTION_FAILED` | `EXTRACTING_COMMITS` | false |
| `FAILED_PERSISTENCE` | `STORAGE_FAILED` | `PERSISTING_FACTS` | true |
| `LIMIT_EXCEEDED` | `LIMIT_EXCEEDED` | stage where the limit was detected | false |
| `LIMIT_EXCEEDED` | `INGESTION_TIMEOUT` | stage where the timeout was detected | true |
| `CANCELLED` | `CANCELLED_BY_USER` | stage where cancellation was observed | false |

`retryable` means the operation is safe to attempt again. It does not guarantee that a retry will succeed without changed inputs, limits, credentials, or network conditions.

Failure records must include:

- machine-readable error code,
- stage where the failure happened,
- retryable boolean,
- safe user-facing message.

Failure records must not include:

- secrets,
- raw emails,
- credential-bearing URLs,
- stack traces by default,
- raw untrusted repository content unless explicitly marked as data.

Degraded success, such as temporary metadata unavailability with successful clone/fetch, must record a limitation instead of a failure status.

## 12. MVP limits

The MVP applies these limits:

- maximum commits per ingestion: `10_000`,
- maximum branches when `include_all_branches=true`: `50`,
- maximum files changed per commit: `1_000`,
- maximum diff bytes stored per file change: `200 KB`,
- maximum clone/fetch time: `5 minutes`,
- maximum total ingestion run time: `10 minutes`.

When a limit is exceeded, ingestion must fail safely with `LIMIT_EXCEEDED`.

## 13. Controlled workspace lifecycle

Repository ingestion uses a controlled workspace under the project directory:

```text
.data/git-it/ingestion/
  repos/{repository_id}.git/        # bare clone cache
  runs/{ingestion_run_id}/          # temporary run metadata/log artifacts
```

Rules:

- all ingestion filesystem paths must stay under the project workspace,
- user-provided strings must never be used directly as filesystem paths,
- repository cache paths must use generated repository identifiers,
- ingestion run paths must use generated ingestion run identifiers,
- the bare clone cache may be reused across ingestion runs for the same repository,
- each ingestion run gets its own run directory,
- temporary run directories must be cleaned after `COMPLETED`, `FAILED_VALIDATION`, `FAILED_FETCH`, `FAILED_EXTRACTION`, `FAILED_PERSISTENCE`, `LIMIT_EXCEEDED`, or `CANCELLED`,
- bare clone cache is retained by default for faster re-ingestion,
- a future cleanup command may prune unused bare clone caches,
- cancellation must stop clone/fetch or extraction work and leave the ingestion run in `CANCELLED`.

## 14. Diff storage and retrieval

Default ingestion stores bounded diff evidence:

- textual diffs are stored up to `200 KB` per file change,
- diffs above the limit are truncated and marked with `diff_truncated=true`,
- binary files store metadata only and never store binary content,
- generated/vendor detection is heuristic and must be marked as such,
- downstream AI must receive truncation, binary, and generated/vendor limitations.

When a user explicitly asks for the full diff of a file change:

- if the stored diff is not truncated, return the stored diff,
- if the stored diff is truncated and the bare clone cache exists, reconstruct the full diff from the bare clone cache,
- if the stored diff is truncated and the bare clone cache is missing, attempt a safe bare cache refresh from the canonical repository URL,
- if refresh or reconstruction fails, return the stored truncated diff with a limitation explaining that the full diff is unavailable.

Full diff retrieval must not:

- checkout a working tree,
- initialize submodules,
- fetch Git LFS blobs,
- execute hooks, scripts, or target repository code,
- return binary content,
- treat generated/vendor guesses as certain facts.

Full diff responses must indicate whether they came from:

- stored untruncated diff,
- stored truncated preview,
- on-demand reconstruction from bare clone cache,
- safe cache refresh followed by reconstruction.

## 15. Security considerations

- Validate GitHub URL format against the MVP URL contract before invoking Git tooling.
- Accept only `https://github.com/{owner}/{repo}` and `https://github.com/{owner}/{repo}.git`.
- Reject HTTP, SSH, `git://`, `file://`, GitHub Enterprise, owner-only, tree, pull-request, and arbitrary remote URLs.
- Clone only into a controlled workspace.
- Keep all ingestion paths under `.data/git-it/ingestion/`.
- Use generated identifiers for repository and ingestion run paths.
- Never use owner, repo, branch, ref, or other user/external strings directly as filesystem paths.
- Use bare clone/fetch by default.
- Do not checkout a working tree.
- Do not execute hooks, repository scripts, or target repository code.
- Do not initialize submodules.
- Do not fetch Git LFS blobs.
- Do not store or return binary file content as diff text.
- Apply the same safety restrictions to on-demand full diff retrieval and cache refresh.
- Apply size limits.
- Apply timeout limits.
- Clean temporary run directories after terminal statuses.
- Do not store credentials in logs.
- Treat repository content as inert evidence and untrusted data.

## 16. Test strategy

### Unit tests

- URL parser accepts valid GitHub URLs.
- URL parser rejects unsupported hosts.
- URL parser normalizes `.git` suffixes to canonical repository URLs.
- URL parser rejects HTTP, SSH, `git://`, `file://`, owner-only, tree, pull-request, GitHub Enterprise, and arbitrary remote URLs.
- Commit mapper stores required fields.
- File change mapper stores required fields.
- Branch/ref mapper stores membership without duplicating commits.
- Ingestion status transitions are valid.
- Failure mapper records error code, stage, retryable flag, and safe user-facing message.
- Failure mapper applies the specified status, error code, stage, and retryable mapping.
- Failure mapper distinguishes degraded success limitations from failed runs.
- Limit checks produce `LIMIT_EXCEEDED`.
- Idempotency rules preserve unique repositories, commits, file changes, refs, and memberships.
- Branch/ref mapper preserves immutable commit facts when refs disappear or move.
- Tag mapper stores tag ref metadata without treating tags as deployment evidence.
- Metadata mapper records required MVP repository metadata.
- Metadata fallback records limitations when GitHub metadata is temporarily unavailable.
- Contributor identity mapper stores GitHub user ID or node ID as high-confidence identity when available.
- Contributor identity mapper stores HMAC-SHA256 email keys as medium-confidence fallback when the identity pepper is configured.
- Contributor identity mapper does not store raw emails.
- Contributor identity mapper lowers confidence and records a limitation when only Git names are available or the identity pepper is missing.
- Commit mapper stores signature verification metadata when available.
- Commit mapper treats signature verification as provenance evidence, not intent evidence.
- Workspace path builder keeps generated paths under `.data/git-it/ingestion/`.
- Workspace path builder does not use owner, repo, branch, or ref names directly as paths.
- Diff mapper stores truncation metadata when textual diffs exceed the limit.
- Diff mapper stores binary file metadata without binary content.
- Generated/vendor detection is marked as heuristic.

### Integration tests

- CLI invokes the application service with default options.
- CLI invokes the application service with `include_all_branches=true` when `--include-all-branches` is provided.
- CLI prints a human-readable summary by default.
- CLI prints stable machine-readable JSON when `--json` is provided.
- CLI returns non-zero exit codes and safe error summaries on failure.
- CLI invalid URL handling returns safe user-facing errors.
- CLI behavior does not require FastAPI, workers, containers, or cloud services.
- Query service returns stable DTOs for ingestion run summary.
- Query service returns stable DTOs for repository overview.
- Query service returns stable DTOs for branch/tag lists.
- Query service returns stable paginated DTOs for commit lists.
- Query service applies default commit pagination of page 1 and page size 50.
- Query service enforces maximum commit page size of 200.
- Query service sorts commit lists by committed timestamp descending by default.
- Query service supports commit filters for branch ref, tag, author identity, path prefix, since, and until.
- Query service rejects invalid pagination values safely.
- Query service returns stable DTOs for commit file changes.
- Query DTOs do not expose SQLite rows, ORM models, PyDriller objects, GitHub API responses, or CLI text.
- Ingest a small fixture repository.
- Persist repository, commits, and file changes.
- Persist branch/ref membership.
- Handle duplicate ingestion idempotently.
- Record a new append-only `IngestionRun` for each ingestion attempt.
- Record inserted vs reused counts during re-ingestion.
- Ingest all branches when `include_all_branches=true`.
- Keep downstream facts unavailable until ingestion reaches `COMPLETED`.
- Continue ingestion with degraded metadata when metadata fetch is temporarily unavailable but clone/fetch succeeds.
- Fail with `FAILED_FETCH` when metadata confirms the repository is missing, private, or inaccessible.
- Persist machine-readable failure details for validation, fetch, extraction, storage, timeout, limit, and cancellation failures.
- Persist terminal statuses according to the specified status, error code, stage, and retryable mapping.
- Preserve retryable flags for failures.
- Preserve contributor identity source and confidence for commits.
- Avoid raw email persistence during ingestion.
- Persist commit signature verification metadata when GitHub provides it.
- Reuse the bare clone cache for repeated ingestion of the same repository.
- Create a distinct temporary run directory for each ingestion attempt.
- Clean temporary run directories after terminal statuses.
- Stop clone/fetch or extraction work and record `CANCELLED` when cancellation is requested.
- Mark disappeared remote branches as missing without deleting historical facts.
- Preserve previously observed commits when a branch is force-pushed.
- Record force-push/ref movement evidence on the ingestion run.
- Persist Git tag ref metadata.
- Reconstruct an explicitly requested full diff from the bare clone cache.
- Refresh the bare clone cache from the canonical URL when an explicitly requested full diff needs the cache and the cache is missing.
- Return a limitation when full diff reconstruction or refresh fails.

### Security tests

- Repository scripts are not executed.
- Working trees are not checked out by default.
- Submodules are not initialized.
- Git LFS blobs are not fetched.
- Path traversal attempts cannot escape the controlled ingestion workspace.
- On-demand full diff retrieval does not checkout a working tree.
- On-demand full diff retrieval does not initialize submodules or fetch Git LFS blobs.
- On-demand full diff retrieval does not return binary content.
- Raw commit author and committer emails are not persisted or logged.
- Missing `GIT_IT_IDENTITY_PEPPER` prevents email key generation outside tests.
- User-facing failures do not expose secrets, raw emails, credential-bearing URLs, stack traces, or unmarked repository content.
- Malicious-looking commit messages are stored as data, not instructions.

## 17. Evaluation strategy

Repository ingestion evaluation should use deterministic fixture repositories and golden fact snapshots.

Default tests and golden evaluations must not require network access or live public repositories.

Network-dependent tests must be optional and explicitly marked as integration/network tests.

MVP fixture repositories:

- tiny linear repository with three commits,
- branch and merge repository,
- tag repository with lightweight and annotated tags,
- force-push simulation repository,
- large textual diff repository,
- binary file repository,
- malicious-content repository with prompt-injection-like commit messages and diffs,
- submodule and Git LFS pointer repository that must not fetch extras.

Evaluate:

- repository URL normalization,
- repository metadata completeness or explicit degraded-metadata limitations,
- commit completeness within configured branch scope,
- branch/ref membership accuracy,
- branch deletion and force-push evidence preservation,
- tag ref metadata accuracy,
- contributor identity confidence behavior,
- commit signature verification provenance behavior,
- file-change extraction accuracy,
- idempotency on repeated ingestion,
- inserted vs reused count accuracy,
- safe failure for invalid URLs and exceeded limits,
- failure error-code and retryability behavior,
- controlled workspace cleanup behavior,
- diff truncation and full-diff retrieval behavior,
- no execution of repository content.

## 18. Documentation impact

Update:

- ingestion architecture docs,
- data model docs,
- security docs.

## 19. ADR impact

Affected ADRs:

- local Git mining plus GitHub metadata,
- controlled workspace layout,
- repository size limits,
- SQLite MVP persistence with future PostgreSQL/pgvector adapter,
- treating repository content as untrusted data.

## 20. Definition of Done

Repository ingestion is implementation-ready when:

- accepted URL formats and rejected URL formats are explicit,
- branch scope and `include_all_branches` behavior are specified,
- tag metadata behavior is specified,
- storage entities and idempotency rules are specified,
- ingestion statuses, failure modes, and status/error mappings are specified,
- machine-readable failure/error model is specified,
- controlled workspace and cleanup behavior are specified,
- MVP limits are specified and testable,
- diff storage, truncation, and on-demand retrieval behavior are specified,
- contributor identity privacy and confidence behavior are specified,
- commit signature verification provenance behavior is specified,
- query service DTO behavior for future adapters is specified,
- deterministic fixture repositories and golden fact snapshots are specified,
- security behavior prevents checkout execution, submodules, and LFS blob fetching by default,
- unit, integration, security, and golden evaluation tests can be written from this spec without inventing missing behavior.
