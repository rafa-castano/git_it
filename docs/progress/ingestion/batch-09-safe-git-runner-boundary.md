## Batch 9 — Safe Git runner boundary

### Goal

Connect the safe Git command planner to an injectable execution boundary without introducing real subprocess execution yet.

### Source of truth

- `docs/specs/001-repository-ingestion.md` failure mappings
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
