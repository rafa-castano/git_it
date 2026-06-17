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
