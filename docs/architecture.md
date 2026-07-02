# Architecture

Git It follows **hexagonal (ports and adapters) architecture** organized as a modular monolith. The domain logic has no framework dependencies — FastAPI, SQLite, LiteLLM, and GitPython are all adapters wired in at composition time.

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
│  SQLite  │  GitPython  │  LiteLLM  │  GitHub API   │
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
  → persist to SQLite

analyze(repository_id)
  → load CommitFacts from SQLite
  → enrich with GitHub context (optional)
  → classify via LiteLLM (CommitAnalysisClient)
  → persist CommitAnalysis records

patterns(repository_id)
  → load CommitFacts + CommitAnalysis from SQLite
  → rule-based detection (hotspots, revert signals, etc.)
  → LLM pattern synthesis (optional)
  → return PatternReport

case-study(repository_id)
  → load PatternReport
  → NarrativeEngine → LLM call
  → persist CaseStudy

API / Dashboard
  → read from SQLite via query readers
  → serve JSON via FastAPI
  → render in Chart.js dashboard
```

## Composition

All wiring happens in `src/git_it/repository_ingestion/composition.py`. Application services receive their dependencies as constructor arguments — no service locator, no global state.

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
  Resolved 2026-07-02 by `specs/014-postgres-read-layer.md`, which introduced
  a PostgreSQL-backed read layer
  (`src/git_it/repository_ingestion/infrastructure/postgres.py`) selected via
  `DATABASE_URL`.

See `ADR/010-local-first-mvp-accepted-limitations.md` for full detail on all
three.

## Roadmap

Open Draft specs describe work that is scoped but not yet built or not yet
fully accepted. These are not commitments or timelines — just the current gap
between what's specified and what's shipped:

- **Spec 005 — Documentation Engine**: automated generation of
  documentation from repository analysis. Not yet built. See
  `specs/005-documentation-engine.md`.
- **Spec 006 — MCP Strategy**: the broader MCP strategy document. The MCP
  server itself is live (ADR 011, spec 011), but this strategy spec covering
  the wider approach is still Draft. See `specs/006-mcp-strategy.md`.
- **Spec 008 — Repository Deletion**: the DELETE endpoint and delete UI are
  built (`src/git_it/api/routes/repos.py`, `src/git_it/static/app.js`), but
  the spec was never bumped past Draft and there is no integration test
  covering the delete flow (`tests/integration/test_repo_lifecycle.py` has no
  delete coverage). See `specs/008-repository-deletion.md`.
