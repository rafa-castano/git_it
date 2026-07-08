# Architecture

Git It follows **hexagonal (ports and adapters) architecture** organized as a modular monolith. The domain logic has no framework dependencies — FastAPI, SQLite, PostgreSQL, LiteLLM, and GitPython are all adapters wired in at composition time.

## Layer overview

```
┌─────────────────────────────────────────────────────┐
│                    CLI / API (FastAPI)               │  ← Driving adapters
├─────────────────────────────────────────────────────┤
│              Application Services                   │  ← Use cases
│  CommitAnalysisService  │  PatternDetectionService  │
│  RepositoryIngestionService  │  NarrativeEngine     │
├─────────────────────────────────────────────────────┤
│                 Domain                              │  ← Pure logic, no I/O
│  CommitFact  │  CommitAnalysis  │  PatternReport    │
│  CaseStudy   │  IngestionRun    │  url_contract     │
├─────────────────────────────────────────────────────┤
│               Infrastructure                        │  ← Driven adapters
│  SQLite/PostgreSQL  │  GitPython  │  LiteLLM  │  GitHub API │
└─────────────────────────────────────────────────────┘
```

## Key ports

| Port | Direction | Description |
|---|---|---|
| `CommitReader` | Driven | Reads raw commits from a git repository |
| `CommitAnalysisClient` | Driven | Calls an LLM to classify and summarize a commit |
| `GithubContextReader` | Driven | Fetches PRs and issues for commit enrichment |
| `IngestionRunStore` | Driven | Persists and queries ingestion run records |
| `CaseStudyStore` | Driven | Stores and retrieves generated case studies |
| `PatternDetector` | Internal | Detects engineering patterns from commit facts |

## Data flow

```
ingest(url)
  → clone/fetch via GitPython
  → extract CommitFacts
  → persist through the configured repository store

analyze(repository_id)
  → load CommitFacts through the configured repository reader
  → enrich with GitHub context (optional)
  → classify via LiteLLM (CommitAnalysisClient)
  → persist CommitAnalysis records

patterns(repository_id)
  → load CommitFacts + CommitAnalysis through configured readers
  → rule-based detection (hotspots, revert signals, etc.)
  → LLM pattern synthesis (optional)
  → return PatternReport

case-study(repository_id)
  → load PatternReport
  → NarrativeEngine → LLM call
  → persist CaseStudy

API / Dashboard
  → read through configured query readers
  → serve JSON via FastAPI
  → render in Chart.js dashboard
```

## Composition

All wiring happens in `src/git_it/repository_ingestion/composition.py`. Application services receive their dependencies as constructor arguments — no service locator, no global state.

Persistence backend selection is centralized at this composition seam:

- no `DATABASE_URL` or a non-PostgreSQL URL → SQLite at `.data/git-it/ingestion/git-it.sqlite3`;
- `DATABASE_URL=postgresql://...` or `postgres://...` → PostgreSQL via psycopg.

Driving adapters such as the API, CLI, MCP server, and chat tools must request readers/stores from composition instead of importing concrete SQLite or PostgreSQL adapters directly. Concrete database imports belong in infrastructure adapters, composition wiring, or adapter-specific tests.

## Architectural decisions

See the [ADR index](adr/index.md) for recorded architectural decisions, including:

- Why spec-driven development was adopted (ADR 001)
- Why a modular monolith was chosen over microservices (ADR 003)
- Why facts and interpretations are stored separately (ADR 004)
- Why structured LLM outputs are required (ADR 005)

## Known limitations

ADR 010 documents the accepted limitations of the local-first, single-process
MVP. Two remain open; one has since been resolved:

- **In-memory progress state** — analyze/regen job progress is held in
  process memory, so it is lost on restart and invisible across multiple
  workers. Still open.
- **Permissive CORS** — the API sets `allow_origins=["*"]`; write endpoints
  are protected by API key, but GET routes are openly readable by design for
  local development. Still open.
- **Direct SQLite reader instantiation in API routes** — routes used to
  construct SQLite readers directly instead of going through a port.
  Resolved 2026-07-02 by `docs/specs/014-postgres-read-layer.md`, which introduced
  a PostgreSQL-backed read layer
  (`src/git_it/repository_ingestion/infrastructure/postgres.py`) selected via
  `DATABASE_URL`. CLI `list-analyses` and the shared MCP/chat tool registry
  also route read-side persistence through composition, so driving adapters no
  longer select SQLite directly.

See `docs/adr/010-local-first-mvp-accepted-limitations.md` for full detail on all
three.

## Roadmap

Open Draft specs describe work that is scoped but not yet built or not yet
fully accepted. These are not commitments or timelines — just the current gap
between what's specified and what's shipped:

- **Spec 005 — Documentation Engine**: automated generation of
  documentation from repository analysis. Not yet built. See
  `docs/specs/005-documentation-engine.md`.
- **Spec 027 — Embedding Backfill**: an explicit, user-triggered action that
  computes embeddings for commit analyses and discussion evidence analyzed
  before `OPENAI_API_KEY` was configured. Implemented (batches 145–148): the
  `EmbeddingBackfillService`, the `git-it backfill-embeddings` CLI command, the
  `GET`/`POST /api/repos/{id}/backfill-embeddings` endpoints, and the
  "Enable semantic search" dashboard button. See
  `docs/specs/027-embedding-backfill.md`.
- **Spec 028 — Refresh All Repositories**: a user-triggered "refresh all"
  action that fetches new commits (fetch + extract only, no analysis) for every
  tracked repository without re-pasting each URL. No scheduler. Implemented
  (batches 150–153): the `RefreshAllService`, the `git-it refresh-all` CLI
  command, the `POST /api/repos/refresh-all` endpoint, and the "Refresh all"
  home dashboard button. See `docs/specs/028-refresh-all-repositories.md`.
