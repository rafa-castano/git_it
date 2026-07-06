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

Open `http://localhost:8000` in your browser. The dashboard has five tabs:

- **Overview** — repository summary, commit category donut chart, commit activity, top hotspots
- **Case Study** — full engineering narrative generated from the commit history
- **Commits** — paginated commit list with LLM-generated category and risk badges
- **Contributors** — per-author contribution stats
- **Ask** — conversational GitItGPT assistant scoped to the open repository

To ingest a repository, use the search bar on the home screen or call the API directly.

## Ask tab (GitItGPT)

The **Ask** tab lets you ask natural-language questions about the open repository
("when did they start adding tests?", "who are the top contributors?") without
leaving the dashboard. Submitting a message calls
`POST /api/repos/{repository_id}/chat/stream`, which runs a bounded, read-only
tool-calling loop (`ChatService`) over the same shared tool layer the MCP server
uses (spec 011) — answers are grounded in real commit SHAs, dates, and counts,
never invented.

- Read-only: the assistant cannot ingest, analyze, regenerate, or delete.
- Repo-scoped: `repository_id` comes from the open repository, never from the
  model.
- Conversation history is kept client-side only (capped at 20 prior turns per
  request); switching repositories starts a fresh conversation.
- The final answer **streams** token-by-token over Server-Sent Events (spec 013,
  ADR 014): a "thinking" indicator covers tool-calling turns (invisible, as
  always) and the initial wait, then is replaced by the answer growing live as
  it's generated. A non-streaming `POST /chat` variant still exists unchanged
  for any other caller.
- The assistant's reply is rendered as sanitized Markdown (`marked.parse()` +
  `DOMPurify.sanitize()`) since repository text — and therefore the model's echo
  of it — is untrusted. This is the same sanitized rendering path Overview and
  Case Study use (ADR 013); it re-renders on every streamed delta.

See `docs/prompt-contracts/gitit-gpt-system-prompt.md`, ADR 012, ADR 013, and
ADR 014 for the system prompt, its injection-hardening rule, the rendering
security model, and the streaming design.

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
| `DATABASE_URL` | No | PostgreSQL connection string (`postgresql://...`); when unset, SQLite is used (default) |

> **Note — Postgres selection is all-or-nothing**: setting `DATABASE_URL` to a
> `postgresql://` or `postgres://` URL switches both the write AND read paths
> to Postgres. If Postgres is selected but unreachable, requests fail loud
> with a 503 diagnostic — there is no silent fallback to SQLite. See
> `docs/specs/014-postgres-read-layer.md`.

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
