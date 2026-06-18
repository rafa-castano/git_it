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
