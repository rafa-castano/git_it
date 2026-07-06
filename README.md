# Git It

Git It turns the history of a public GitHub repository into an evidence-based engineering case study.

Instead of only explaining what a codebase looks like today, it mines commits, file changes, contributors and repository context over time, then uses LLMs to explain how the project evolved and which technical patterns shaped that evolution.

## Main features

- Ingest public GitHub HTTPS repositories into a local bare Git cache.
- Extract commit facts: SHA, dates, messages, authors, parents and changed files.
- Analyze commits with structured LLM outputs.
- Detect evolution patterns such as hotspots, refactor waves, reverts, test-growth signals, dependency migrations and architectural shifts.
- Generate narrative case studies for different audiences.
- Explore a repository through a FastAPI API, browser dashboard, CLI, Ask assistant and read-only MCP server.

## Tech stack

- **Language:** Python 3.12+
- **API:** FastAPI + Uvicorn
- **Git analysis:** GitPython and the local Git CLI
- **Persistence:** SQLite by default; PostgreSQL optional via SQLAlchemy/psycopg
- **LLM layer:** LiteLLM + Instructor
- **Frontend:** static HTML/CSS/JavaScript dashboard with Chart.js
- **MCP:** Python MCP SDK, exposed through `git-it mcp`
- **Quality tools:** pytest, pytest-cov, ruff, mypy and pre-commit

## Requirements

- Python 3.12 or newer.
- Git installed and available in `PATH`.
- [`uv`](https://docs.astral.sh/uv/) for dependency management.
- An LLM provider key for LLM-backed features. The project is configured primarily around Anthropic-compatible chat models via LiteLLM.

## Installation

```bash
git clone <repository-url>
cd <repository-folder>
uv sync
```

For documentation tooling:

```bash
uv sync --group docs
```

## Configuration

Create a `.env` file in the project root when you need local configuration:

```env
# Required for LLM-backed commit analysis, narratives and Ask
ANTHROPIC_API_KEY=

# Optional: enrich repository context from GitHub
GITHUB_TOKEN=

# Optional: protect write endpoints with Authorization: Bearer <token>
# Leave unset for local dashboard development.
GIT_IT_API_KEY=

# Optional: custom data directory. Defaults to .data/git-it/ingestion
GIT_IT_DATA_DIR=

# Optional: use PostgreSQL instead of SQLite.
# Leave unset for the default local SQLite database.
DATABASE_URL=

# Optional: enables embedding-backed semantic search when configured
OPENAI_API_KEY=
```

> Note: if `DATABASE_URL` points to PostgreSQL, Git It expects that database to be reachable. It does not silently fall back to SQLite.

## Run the dashboard and API

```bash
uv run git-it serve --host 127.0.0.1 --port 8000
```

Then open:

- Dashboard: <http://localhost:8000>
- OpenAPI docs: <http://localhost:8000/docs>

Alternative development entry point:

```bash
uv run uvicorn git_it.api.app:app --reload
```

## CLI usage

The CLI expects full public GitHub repository URLs, for example `https://github.com/owner/repo`.

```bash
REPO=https://github.com/owner/repo

uv run git-it ingest "$REPO"
uv run git-it analyze-commits "$REPO" --limit 20 --yes
uv run git-it patterns "$REPO"
uv run git-it case-study "$REPO"
```

Run the complete local pipeline:

```bash
uv run git-it run "$REPO" --limit 20 --yes
```

Other useful commands:

```bash
uv run git-it commits "$REPO" --limit 50
uv run git-it list-analyses "$REPO"
uv run git-it serve
uv run git-it mcp
```

## Project structure

```text
src/git_it/
  api/                    FastAPI app, routes, auth and dependency wiring
  chat/                   Ask assistant and LLM tool-calling loop
  mcp/                    Read-only Git It MCP server
  repository_ingestion/   Core ingestion, analysis and narrative module
    domain/               Framework-free domain models and rules
    application/          Use cases, services and ports
    infrastructure/       Git, database, GitHub and LLM adapters
    interfaces/           CLI and external entry points
  static/                 Browser dashboard assets
  tools/                  Shared read-only tool definitions

docs/                     Architecture, ADRs, MCP notes and user docs
migrations/               Database schema migrations
scripts/                  Local helper scripts
specs/                    Product/engineering specifications
tests/                    Unit and integration tests
```

The core module follows a ports-and-adapters style: domain and application code stay independent from FastAPI, Git providers, databases and LLM clients. Concrete adapters are composed at the edges.

## Data storage

By default, local data is stored under:

```text
.data/git-it/ingestion/
```

This includes the SQLite database and the bare Git repository cache. Set `GIT_IT_DATA_DIR` to move this directory. Set `DATABASE_URL` only when you want PostgreSQL.

A Docker Compose setup is also available for running the API with PostgreSQL:

```bash
docker compose up
```

## MCP server

Git It can run as a read-only MCP server:

```bash
uv run git-it mcp
```

Available tools include:

- `list_repositories`
- `get_case_study`
- `get_patterns`
- `search_commits`
- `get_contributors`

These tools expose stored Git It analysis data to MCP-compatible clients without mutating repositories or Git history.

## Development checks

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```

Documentation can be served locally with:

```bash
uv run mkdocs serve
```

## Current scope and limitations

- Repository ingestion is focused on public GitHub HTTPS repositories.
- LLM-backed features require provider credentials and may incur external API costs.
- Some features are intentionally read-only through MCP to keep repository analysis safe.
- Local development defaults to SQLite; production-like deployments should use PostgreSQL and explicit API authentication.
