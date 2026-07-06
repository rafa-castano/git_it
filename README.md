![Git It Logo](src/git_it/static/git_it_logo_detail_eng.png)

**Git It turns the history of a public GitHub repository into an evidence-based engineering case study.**

It mines commits, file changes, contributors and repository context over time, then uses LLMs to explain *how* a project evolved, which patterns emerged, and what a learner or engineering team can take from that history — every claim linked back to the commits, patterns, discussions, releases or advisories that support it.

## Screenshots

| Home (dark) | Repository overview (light) |
|---|---|
| ![Git It home dashboard](docs/assets/screenshots/readme-home.png) | ![Repository overview](docs/assets/screenshots/readme-overview.png) |
| **Case study (light)** | **Ask assistant (light)** |
| ![Generated case study](docs/assets/screenshots/readme-case-study.png) | ![Ask assistant](docs/assets/screenshots/readme-ask.png) |

---

## Get started in 5 steps

This is the complete path from nothing to your first case study. You need **Python 3.12+**, **Git**, and [**uv**](https://docs.astral.sh/uv/) on your `PATH`, plus an **Anthropic API key** (the LLM features run on Anthropic by default).

**1. Clone and install**

```bash
git clone <repository-url>
cd git_it
uv sync
```

**2. Add your API key**

Copy the template and open `.env` in an editor:

```bash
cp .env.example .env
```

Set just this one line to get running (Git It loads `.env` automatically — you don't need to export anything):

```env
ANTHROPIC_API_KEY=your_anthropic_key
```

> Everything else in `.env` is optional. Leave `GIT_IT_API_KEY` **blank** for local use — if you set it, the dashboard's buttons stop working because they don't send an auth header (see [Environment variables](#environment-variables)).

**3. Start the app**

```bash
uv run git-it serve --host 127.0.0.1 --port 8000
```

**4. Open the dashboard** at <http://localhost:8000> (API docs live at <http://localhost:8000/docs>).

**5. Analyze your first repository**

1. Paste a public GitHub URL (`https://github.com/owner/repo`, or just `owner/repo`) and click **Analyze**. Git It clones the repo as a local bare cache and extracts commit facts.
2. Open the repository from the list, click **+ Analyze**, and pick how many commits to analyze — **start with 10–20**. More commits means richer analysis but more time and more LLM calls.
3. When the background job finishes, explore the **Overview**, **Commits**, **Case Study**, **Contributors** and **Ask** tabs.

That's it. The two actions are deliberately separate: **Analyze on the home page** downloads Git data (free); **+ Analyze inside a repo** spends LLM calls on not-yet-analyzed commits.

---

## What you can do

- **Ingest** any public GitHub HTTPS repository into a local bare Git cache.
- **Analyze** selected commits into structured, LLM-generated summaries (beginner and expert audiences).
- **Detect patterns**: hotspots, refactor waves, reverts, test-growth, recurring bugfixes, ownership concentration, dependency migrations and architectural shifts.
- **Generate narrative case studies**, grounded in cited evidence (commits, GitHub discussions, releases and security advisories).
- **Ask questions** about an analyzed repository through a tool-using assistant.
- Reach the same stored analysis through the **dashboard, CLI, REST API and a read-only MCP server**.

## Everyday use

- **Add new commits from GitHub** — paste the same repository URL on the home page again. Git It runs `git fetch` to update the local cache, then click **+ Analyze** to process the pending commits.
- **Ask** — the Ask tab answers from stored commits, patterns, contributors and case studies (needs `ANTHROPIC_API_KEY`). Add `OPENAI_API_KEY` to also enable **semantic search** over embedded summaries. Embeddings are created *during analysis*, so configure OpenAI **before** analyzing a repo if you want semantic Ask for it — old analyses are not backfilled automatically.
- **Case study audience** — switching audience in the Case Study tab reuses a cached narrative or regenerates one (an LLM call).
- **Delete** — removes Git It's stored analysis for a repository. It never touches the upstream GitHub repo.

## Environment variables

`.env.example` documents every variable with inline comments — it's the full reference. The ones you'll actually think about:

| Variable | Set it when… | Effect |
|---|---|---|
| `ANTHROPIC_API_KEY` | Always (for any LLM feature) | Powers commit analysis, case studies, and the Ask tab. |
| `OPENAI_API_KEY` | You want semantic search in Ask | Enables embeddings + `search_similar_commits`. |
| `GITHUB_TOKEN` | You want richer GitHub evidence | Adds stars/languages, PR/issue context, discussions, releases and security advisories. **Not** a private-repo credential. |
| `DATABASE_URL` | You want PostgreSQL | Selects Postgres; otherwise Git It uses local SQLite. No silent fallback if Postgres is unreachable. |
| `GIT_IT_API_KEY` | You expose the API to others | Requires `Authorization: Bearer <token>` on write/cost endpoints. **Leave blank for local dashboard use.** |

Advanced tuning knobs (`EMBEDDING_MODEL`, `PROJECT_DOC_MAX_CHARS`, `GIT_IT_DATA_DIR`, the `DISCUSSION_*` / `RELEASE_MAX_SUMMARIZED` / `ADVISORY_MAX_SUMMARIZED` limits) have sensible defaults — see `.env.example`.

**Direct API call** when `GIT_IT_API_KEY` is set:

```bash
curl -X POST http://localhost:8000/api/repos/{repository_id}/analyze \
  -H "Authorization: Bearer $GIT_IT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"limit": 50, "audience": "beginner"}'
```

## CLI

Everything the dashboard does is also scriptable. Commands take a full public GitHub URL.

```bash
REPO=https://github.com/owner/repo

uv run git-it run "$REPO" --limit 20 --yes   # full pipeline: ingest + analyze + case study
```

Or run the stages individually:

```bash
uv run git-it ingest "$REPO"                     # clone/fetch + extract commit facts
uv run git-it analyze-commits "$REPO" --limit 20 --yes
uv run git-it patterns "$REPO"
uv run git-it case-study "$REPO"
```

Query stored data:

```bash
uv run git-it commits "$REPO" --limit 50
uv run git-it list-analyses "$REPO"
```

Servers: `uv run git-it serve` (dashboard/API) and `uv run git-it mcp` (read-only MCP over stdio).

## Data and databases

By default Git It uses **SQLite**, storing the database and the bare Git cache under `.data/git-it/ingestion/`.

For **PostgreSQL**, set `DATABASE_URL`:

```env
DATABASE_URL=postgresql://gitit:gitit@localhost:5432/gitit
```

A `docker compose up` setup is provided for a Postgres-backed run — pass your LLM provider keys to the API container as environment variables.

## MCP server

`uv run git-it mcp` exposes stored analysis as read-only MCP tools over stdio: `list_repositories`, `get_case_study`, `get_patterns`, `search_commits`, `get_contributors`. They only read already-stored data — no ingestion, no LLM calls, no writes.

## Troubleshooting

- **Dashboard buttons return 401/403** → `GIT_IT_API_KEY` is set. Leave it blank for local use.
- **Semantic Ask finds nothing** → set `OPENAI_API_KEY`, then re-analyze the repo (old analyses aren't backfilled with embeddings).
- **New GitHub commits don't show up** → paste the repo URL again on the home page to fetch, then **+ Analyze**.
- **PostgreSQL errors on startup** → unset `DATABASE_URL` for SQLite, or start/fix Postgres. Git It won't fall back silently.
- **Private repo fails** → ingestion targets public GitHub HTTPS repos; `GITHUB_TOKEN` enriches metadata but is not used as clone credentials.

## Tech stack

Python 3.12+ · FastAPI + Uvicorn · GitPython + Git CLI · SQLite (PostgreSQL optional via psycopg) · LiteLLM + Instructor · static HTML/CSS/JS dashboard with Chart.js · Python MCP SDK · pytest, ruff, mypy, pre-commit.

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

docs/                     User docs, architecture, ADRs (docs/adr/), specs (docs/specs/), progress log
migrations/               Database schema migrations
tests/                    Unit and integration tests
```

The core follows a ports-and-adapters style: domain and application code stay independent of FastAPI, Git, databases and LLM clients; concrete adapters are composed at the edges.

## Development

```bash
uv run pytest
uv run ruff check .
uv run mypy src
uv sync --group docs && uv run mkdocs serve   # docs site at http://localhost:8000
```

## Scope and limitations

- Ingestion targets **public** GitHub HTTPS repositories.
- LLM-backed features need provider credentials and can incur external API costs.
- MCP exposure is intentionally **read-only**.
- Local defaults to SQLite; shared deployments should use `GIT_IT_API_KEY` and a managed database.
