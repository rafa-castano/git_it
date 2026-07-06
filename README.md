![Git It Logo](src/git_it/static/git_it_logo_detail_eng.png)

Git It turns the history of a public GitHub repository into an evidence-based engineering case study.

Instead of only explaining what a codebase looks like today, Git It mines commits, file changes, contributors and repository context over time, then uses LLMs to explain how the project evolved, which patterns appeared, and what a learner or engineering team can take away from that history.

## Screenshots

### Home (dark mode)

![Git It home dashboard](docs/assets/screenshots/readme-home.png)

### Repository overview (light mode)

![Repository overview with commit categories, activity and hotspots](docs/assets/screenshots/readme-overview.png)

### Case study (light mode)

![Generated repository case study](docs/assets/screenshots/readme-case-study.png)

### Ask assistant (light mode)

![Ask assistant for repository questions](docs/assets/screenshots/readme-ask.png)

## What you can do with it

- Ingest public GitHub HTTPS repositories into a local bare Git cache.
- Extract commit facts: SHA, dates, messages, authors, parents and changed files.
- Analyze selected commits with structured LLM outputs.
- Detect evolution patterns: hotspots, refactor waves, reverts, test-growth signals, recurring bugfixes, ownership concentration, dependency migrations and architectural shifts.
- Generate narrative case studies for different audiences.
- Ask questions about an analyzed repository through a tool-using assistant.
- Use the same stored analysis through the browser dashboard, CLI, REST API and read-only MCP server.

## Quick start: local dashboard

Use this path if you cloned the repository and want to analyze repositories locally.

### 1. Requirements

- Python 3.12 or newer.
- Git available in `PATH`.
- [`uv`](https://docs.astral.sh/uv/) for dependency management.
- At least one LLM provider key:
  - `ANTHROPIC_API_KEY` is required for commit analysis, case-study generation and the Ask tab LLM.
  - `OPENAI_API_KEY` is required only if you want embedding-backed semantic search in Ask.

### 2. Install

```bash
git clone <repository-url>
cd <repository-folder>
uv sync
```

### 3. Configure environment variables

Copy the example file and fill the variables for your use case:

```bash
cp .env.example .env
```

Minimum local setup:

```env
ANTHROPIC_API_KEY=your_anthropic_key
```

Recommended setup if you also want semantic search in Ask:

```env
OPENAI_API_KEY=your_openai_key
```

Do **not** set `GIT_IT_API_KEY` for normal local dashboard usage. When that variable is set, protected endpoints require an `Authorization: Bearer ...` header, and the current static dashboard does not send that header.

See [Environment variables](#environment-variables) for every supported variable.

### 4. Run

```bash
uv run git-it serve --host 127.0.0.1 --port 8000
```

Open:

- Dashboard: <http://localhost:8000>
- OpenAPI docs: <http://localhost:8000/docs>

Alternative development entry point:

```bash
uv run uvicorn git_it.api.app:app --reload
```

## Main user flows

### Analyze a repository for the first time

Use this flow when the repository has never been analyzed by your local Git It instance.

1. Open <http://localhost:8000>.
2. Paste a public GitHub repository URL, for example `https://github.com/owner/repo`. The dashboard also accepts `owner/repo`.
3. Click `Analyze` on the home page. This starts ingestion: Git It clones the repository as a local bare Git cache and extracts commit facts.
4. Open the repository detail page once ingestion appears in the list.
5. Click `+ Analyze` and choose how many commits to analyze with the LLM.
6. Wait for the background analysis to finish. The dashboard will then populate commit summaries, patterns, contributors and the case study.

For a first run, start with 10 or 20 commits. Larger limits produce richer analysis, but they take longer and spend more LLM calls.

### Update an existing repository with new commits

Use this flow when the repository already exists in Git It but new commits were pushed to GitHub.

1. Paste the same repository URL again in the home form.
2. Git It detects the existing local bare cache and runs `git fetch` to update remote refs and stored commit facts.
3. Open the repository detail page.
4. Click `+ Analyze` to process commits that do not have analysis yet.

The split is intentional: **ingest/fetch** updates local Git data; **Analyze** spends LLM calls on not-yet-analyzed commits.

### Use Ask

The Ask tab has two levels:

- **Basic Ask** requires `ANTHROPIC_API_KEY`. It can answer using stored commits, patterns, contributors and case studies through read-only repository tools.
- **Semantic Ask / RAG** additionally requires `OPENAI_API_KEY`. When configured, Git It generates embeddings during analysis and enables semantic search over embedded commit/discussion summaries.

Important: embeddings are created when commits are analyzed. If commits were analyzed before `OPENAI_API_KEY` was configured, those old analyses are not automatically backfilled with embeddings by the current workflow. Configure OpenAI before analyzing if semantic Ask matters for that repository.

### Regenerate or change the case-study audience

Case studies are generated from stored commit analysis and pattern data. If you change the audience in the Case Study tab, Git It may reuse a cached narrative or start a regeneration for that audience. This uses LLM calls, so `ANTHROPIC_API_KEY` must be configured.

### Delete local repository data

The dashboard includes delete actions for locally stored repository data. This removes Git It's stored analysis for that repository; it does not mutate the upstream GitHub repository.

If `GIT_IT_API_KEY` is enabled, delete actions are protected like other write endpoints and require direct API calls with `Authorization: Bearer <token>`.

## Environment variables

`.env.example` lists every supported variable with comments. The most common cases are:

| Variable | Required when | What it does |
|---|---|---|
| `ANTHROPIC_API_KEY` | Commit analysis, case studies, Ask LLM | Used by LiteLLM for the default Anthropic chat models. |
| `OPENAI_API_KEY` | Semantic Ask / embeddings | Enables embedding generation and `search_similar_commits`. |
| `GITHUB_TOKEN` | Optional GitHub enrichment | Fetches stars/languages, PR/issues context and discussion evidence where available. It does not enable private repo cloning. |
| `GIT_IT_API_KEY` | Shared/API deployment only | Protects write/cost endpoints with `Authorization: Bearer <token>`. Leave blank for local dashboard use. |
| `GIT_IT_DATA_DIR` | Custom data root | Moves local app data when using `uvicorn`/API composition. `git-it serve` roots data at the current working directory. |
| `DATABASE_URL` | PostgreSQL deployment | Selects PostgreSQL. Leave blank for local SQLite. No silent fallback if PostgreSQL is unreachable. |
| `EMBEDDING_MODEL` | Advanced embedding override | Defaults to OpenAI's `text-embedding-3-small`. |
| `PROJECT_DOC_MAX_CHARS` | Advanced prompt-size tuning | Controls how much root README/CHANGELOG text is injected as repository context. |
| `DISCUSSION_*`, `RELEASE_MAX_SUMMARIZED`, `ADVISORY_MAX_SUMMARIZED` | Advanced GitHub evidence tuning | Controls bounded GitHub evidence collection. Usually leave defaults. |

### API authentication with `GIT_IT_API_KEY`

Do not set this for normal local dashboard usage.

Set it only if you expose the API to someone else or run Git It in a shared environment. When set, these actions require a bearer token: ingesting repositories, analyzing commits, regenerating case studies, using Ask and deleting repositories.

Example direct API call:

```bash
curl -X POST http://localhost:8000/api/repos/{repository_id}/analyze \
  -H "Authorization: Bearer $GIT_IT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"limit": 50, "audience": "beginner"}'
```

## CLI usage

The CLI expects full public GitHub repository URLs.

```bash
REPO=https://github.com/owner/repo
```

First ingest a repository:

```bash
uv run git-it ingest "$REPO"
```

Analyze commits:

```bash
uv run git-it analyze-commits "$REPO" --limit 20 --yes
```

Generate patterns and a case study:

```bash
uv run git-it patterns "$REPO"
uv run git-it case-study "$REPO"
```

Run the common pipeline in one command:

```bash
uv run git-it run "$REPO" --limit 20 --yes
```

Useful query commands:

```bash
uv run git-it commits "$REPO" --limit 50
uv run git-it list-analyses "$REPO"
```

Server commands:

```bash
uv run git-it serve
uv run git-it mcp
```

## Data storage and databases

By default, Git It uses SQLite and stores local data under:

```text
.data/git-it/ingestion/
```

That directory contains the SQLite database and the bare Git repository cache.

Set `DATABASE_URL` only when you want PostgreSQL:

```env
DATABASE_URL=postgresql://gitit:gitit@localhost:5432/gitit
```

If `DATABASE_URL` starts with `postgresql://` or `postgres://`, Git It selects PostgreSQL and expects it to be reachable. It will not silently fall back to SQLite.

A Docker Compose file is provided for a PostgreSQL-backed setup:

```bash
docker compose up
```

If you use Docker Compose for LLM-backed features, make sure the API container receives the provider keys as environment variables.

## MCP server

Git It can also run as a read-only MCP server over stdio:

```bash
uv run git-it mcp
```

Available tools:

- `list_repositories`
- `get_case_study`
- `get_patterns`
- `search_commits`
- `get_contributors`

These tools expose already stored Git It analysis data. They do not ingest repositories, trigger LLM analysis, regenerate narratives, delete data or mutate Git history.

## Tech stack

- **Language:** Python 3.12+
- **API:** FastAPI + Uvicorn
- **Git analysis:** GitPython and the local Git CLI
- **Persistence:** SQLite by default; PostgreSQL optional via SQLAlchemy/psycopg
- **LLM layer:** LiteLLM + Instructor
- **Frontend:** static HTML/CSS/JavaScript dashboard with Chart.js
- **MCP:** Python MCP SDK
- **Quality tools:** pytest, pytest-cov, ruff, mypy and pre-commit

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

## Development checks

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```

Documentation can be served locally with:

```bash
uv sync --group docs
uv run mkdocs serve
```

## Troubleshooting

- **Dashboard actions return 401/403:** `GIT_IT_API_KEY` is probably set. Leave it blank for local dashboard use, or call the API directly with `Authorization: Bearer <token>`.
- **Ask works but semantic search returns no similar commits:** configure `OPENAI_API_KEY` before analyzing commits. Existing analyzed commits are not automatically backfilled with embeddings.
- **New GitHub commits do not appear:** paste the same repository URL again on the home page to trigger fetch/ingestion, then run `+ Analyze` for pending commits.
- **PostgreSQL errors on startup:** unset `DATABASE_URL` to use SQLite locally, or start/fix the PostgreSQL instance. Git It does not fall back to SQLite when PostgreSQL is selected.
- **Private repository fails:** current ingestion is focused on public GitHub HTTPS repositories. `GITHUB_TOKEN` enriches metadata/context; it is not used as Git clone credentials.

## Current scope and limitations

- Repository ingestion is focused on public GitHub HTTPS repositories.
- LLM-backed features require provider credentials and may incur external API costs.
- MCP exposure is intentionally read-only.
- Local development defaults to SQLite; shared deployments should use explicit API authentication and a managed database.