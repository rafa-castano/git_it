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
