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
