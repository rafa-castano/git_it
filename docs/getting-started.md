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

```bash
uv run uvicorn main:app --reload
```

The API is now available at `http://localhost:8000`.

## Using the dashboard

Open `http://localhost:8000` in your browser. The dashboard has four tabs:

- **Overview** — repository summary, contributor breakdown, commit category donut chart
- **Commits** — paginated commit list with LLM-generated category and risk badges
- **Patterns** — detected patterns: hotspots, refactor waves, revert signals, ownership concentration
- **Case Study** — full engineering narrative generated from the commit history

To ingest a repository, use the search bar on the home screen or call the API directly.

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
