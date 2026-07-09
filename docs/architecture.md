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
- **Spec 029 — Verified File/Folder Path Linking**: grounds case-study and chat
  file links in the repository's real file tree (captured via `git ls-tree` at
  ingest/refresh) so a span links only when the path actually exists — superseding
  spec 020's "link optimistically" posture with tree-verified, no-broken-link
  linking. Implemented (batch 157): the `FileTreeReader`/`FileTreeWriter` ports +
  `repository_files` store, `GET /api/repos/{id}/file-paths`, the tree-verified
  `_linkifyPaths` frontend, and the full-repo-relative-path prompt rule. See
  `docs/specs/029-verified-file-path-linking.md`.
- **Spec 030 — Incremental Commit Extraction**: makes ingest re-extract only the
  commits it does not already have. The service reads the stored commit SHAs
  through a new lightweight `StoredCommitShaReader` port and passes them to the
  extractor as a skip-set; `GitPythonCommitExtractor` skips both the
  `ExtractedCommit` build and the expensive per-commit `git diff`
  (`commit.stats`) for any skipped SHA, so **Refresh all** and re-ingest cost
  tracks the number of new commits, not total history size. Append-only: stored
  facts after an incremental ingest are identical to a full ingest of the same
  history (orphan commits from upstream history rewrites are tolerated, not
  pruned). Implemented (batch 159): the `StoredCommitShaReader` port,
  `Sqlite`/`PostgresStoredCommitShaReader` adapters, the extractor skip-set, and
  the AC-11 degrade-to-full-extraction fallback. See
  `docs/specs/030-incremental-commit-extraction.md`.
- **Spec 031 — Contributor GitHub Login Resolution**: makes a contributor card
  link to the real GitHub **profile** (`github.com/{login}`) instead of a user
  search page. The login is resolved from the REST **List commits** endpoint
  (top-level `author.login` paired with `commit.author.email`, for commits GitHub
  can match to an account) and stored per repository as an `author_email → login`
  map; the contributor read model prefers a stored login over the noreply-email
  heuristic, so the frontend links to the profile with no change. Resolution is
  incremental (only never-attempted emails are queried; `null`-author emails get a
  stored "attempted, no match" marker) and token-gated, best-effort, and
  failure-isolated — it runs only in the `_ingest_bg` enrichment block, so
  "Refresh all" incurs zero login-resolution calls. Resolved logins are
  charset-validated (`^[A-Za-z0-9-]+$`) as untrusted input. Implemented (batch
  160): the `GithubCommitAuthorsFetcher`, the `AuthorLoginStore` port +
  `Sqlite`/`PostgresAuthorLoginStore` adapters (`author_logins` table), the
  `_fetch_and_store_commit_author_logins` hook, and the contributor-reader
  precedence. See `docs/specs/031-contributor-github-login-resolution.md`.
