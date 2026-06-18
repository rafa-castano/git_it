## Batch 59 — GitHub Actions CI workflow and Dockerfile

### Goal

Add a reproducible CI pipeline and a production-ready container image for Git It. Both use `uv` as the single tool for dependency management, matching the project's existing toolchain.

### What was added

**`.github/workflows/ci.yml`**
- Triggers on every push and pull_request to `main`.
- Single job (`ci`) on `ubuntu-latest` with Python 3.12.
- Uses `astral-sh/setup-uv@v5` to install `uv`; then `uv sync --frozen` to reproduce the locked environment exactly.
- Steps in order:
  1. `ruff check src/ tests/` — lint for errors and style violations.
  2. `ruff format --check src/ tests/` — enforce formatting without modifying files.
  3. `mypy src/` — static type checking.
  4. `pytest tests/ -x -q` — full test suite with coverage (flags come from `pytest.ini`).
- Uploads `.coverage` as an artifact (`coverage-report`, 7-day retention) so coverage data is available for downstream inspection even when the job succeeds.

**`Dockerfile`**
- Two-stage build: `builder` and `runner`, both from `python:3.12-slim`.
- `builder`: copies `uv` binary from `ghcr.io/astral-sh/uv:latest`, copies `pyproject.toml` + `uv.lock`, runs `uv sync --frozen --no-dev` to install only production dependencies into `.venv`.
- `runner`: copies `/app/.venv` from builder, copies `src/`, sets `PYTHONUNBUFFERED=1` and `PYTHONDONTWRITEBYTECODE=1`, exposes port 8000.
- Entry point: `uvicorn git_it.api.app:app --host 0.0.0.0 --port 8000 --app-dir src`.
- No dev dependencies, no test files, no docs in the final image.

**`.dockerignore`**
Excludes: `.git`, `__pycache__`, `*.pyc`, `*.pyo`, `.venv`, `tests/`, `docs/`, `specs/`, `.data/`, `*.md`, `.claude/`, `.playwright-mcp/`.

### Decisions made

| Decision | Rationale |
|---|---|
| Single job (not matrix of jobs) | Small project — parallelism adds overhead without meaningful benefit. All steps run sequentially in one job, keeping the workflow fast and simple. |
| `uv sync --frozen` in CI | Reproducible builds: lock file is the source of truth. Never auto-upgrades. |
| `uv sync --no-dev` in Docker | Keeps the production image lean — drops `pytest`, `mypy`, `ruff`, `hypothesis`, etc. |
| `astral-sh/setup-uv@v5` | Official uv GitHub Action; handles PATH setup, caching, and Python installation in one step. |
| Coverage artifact upload with `if: always()` | Ensures the artifact is uploaded even if pytest exits non-zero so partial coverage data is recoverable. |
| Two-stage Dockerfile | Layer caching: dependency install is a separate stage from the source copy. A code change only rebuilds the runner stage, not the full dependency install. |
| `ghcr.io/astral-sh/uv:latest` for uv in Docker | Official uv image; simplest way to get the binary without a shell script. |

### Tests added

No new tests — this batch adds infrastructure files only.

### Commits

- `feat: add GitHub Actions CI workflow and Dockerfile`
