# Getting Started

## Prerequisites

- **Python 3.12+**
- **uv** — fast Python package manager ([install](https://docs.astral.sh/uv/))
- **GITHUB_TOKEN** (optional) — enables GitHub context enrichment (PR and issue injection into analysis)

## Installation

```bash
# Clone the repository
git clone https://github.com/your-org/git-it
cd git-it

# Install dependencies
uv sync
```

## Running the server

First, activate the project virtual environment:

```bash
# Windows (PowerShell)
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

Then start the server:

```bash
uvicorn git_it.api.app:app --reload
```

The API is now available at `http://localhost:8000`.

> **Note — `uv run` and global venvs**: if you have another virtual environment active in your
> shell (e.g. a global `~/.venv`), `uv run uvicorn …` will use that environment instead of the
> project's `.venv` and fail with `ModuleNotFoundError: No module named 'git_it'`. Activating
> the project venv explicitly (as shown above) avoids this. Alternatively, you can invoke the
> project venv's executables directly without activating:
>
> ```bash
> # Windows
> .venv\Scripts\uvicorn git_it.api.app:app --reload
>
> # macOS / Linux
> .venv/bin/uvicorn git_it.api.app:app --reload
> ```

## Using the dashboard

Open `http://localhost:8000` in your browser. The dashboard has four tabs:

- **Overview** — repository summary, contributor breakdown, commit category donut chart
- **Commits** — paginated commit list with LLM-generated category and risk badges
- **Patterns** — detected patterns: hotspots, refactor waves, revert signals, ownership concentration
- **Case Study** — full engineering narrative generated from the commit history

To ingest a repository, use the search bar on the home screen or call the API directly.

## MCP server (read-only)

Git It can expose its analyzed domain to any MCP client (Claude Desktop, Codex) as a
read-only stdio server:

```bash
git-it mcp
```

This publishes five read-only tools (`list_repositories`, `get_case_study`,
`get_patterns`, `search_commits`, `get_contributors`) backed by the same data the
REST API serves. It reads the database resolved from `GIT_IT_DATA_DIR` and never
mutates data, spends LLM budget, or exposes secrets. See `docs/mcp/servers.md` and
ADR 011 for the client config and security model.

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `GIT_IT_API_KEY` | Yes (for write endpoints) | Bearer token for protected API routes (`/ingest`, `/analyze`) |
| `GITHUB_TOKEN` | No | GitHub personal access token — enables PR/issue context in analysis |
| `PROJECT_ROOT` | No | Override the workspace root directory (default: current working directory) |

## CLI usage

```bash
# Ingest a repository by URL
uv run git-it ingest https://github.com/your-org/your-repo

# Query ingested commits
uv run git-it commits <repository_id>

# Run LLM commit analysis
uv run git-it analyze <repository_id>

# Generate a case study
uv run git-it case-study <repository_id>

# Run full pipeline (ingest + analyze + case study)
uv run git-it run <url>
```
