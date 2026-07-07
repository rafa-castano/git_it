## Batch 147 — Embedding backfill status/run API endpoints (spec 027, slice 3)

### Goal

Expose `EmbeddingBackfillService` (batch 145) on the API surface: a status/availability
endpoint the future dashboard button (batch 148) can poll to decide its own visibility, and a
run endpoint that triggers the backfill for a repository. Slice 3 of spec 027's build order
(backfill service → CLI command → **API endpoint** → dashboard control); the dashboard control
itself is out of scope here and lands in batch 148.

### Why

Slice 2 gave operators a CLI command; the API needs the same capability so the dashboard can
offer a one-click "enable semantic search for this repo" control without shelling out to the
CLI, and so the dashboard can decide when to show that control at all.

### What was added

**`src/git_it/api/schemas.py`**
- `BackfillEmbeddingsStatusResponse` (`available: bool`, `missing: int`) — the GET response.
- `BackfillEmbeddingsResponse` (`embedded: int`, `already_present: int`, `failed: int`) — the
  POST response, mirroring `EmbeddingBackfillResult`'s three fields exactly.

**`src/git_it/api/routes/repos.py`**
- `GET /api/repos/{repository_id}/backfill-embeddings` — gated by `_require_repository_exists`
  (same 404 pattern as `estimate_analyze`/`get_patterns`/`get_commits`), rate-limited
  `20/minute` (mirrors `estimate_analyze`). Builds the service via
  `build_embedding_backfill_service(project_root=project_root)` and returns
  `available=service.is_available`, `missing=service.estimate_backfill_calls(repository_id)`.
  This is the visibility signal batch 148's dashboard button will poll.
- `POST /api/repos/{repository_id}/backfill-embeddings` — same 404 gate, rate-limited
  `10/minute` (mirrors `trigger_analyze`), protected by `Depends(require_api_key)` (same auth
  dependency as `trigger_analyze`/`delete_repo`/`regenerate_case_study`). Builds the service,
  and:
  - if `service.is_available` is `False` (no `OPENAI_API_KEY`): raises
    `HTTPException(503, "Embedding backfill unavailable: OPENAI_API_KEY is not configured.")`
    — never a silent/fake success (spec 027 AC "No OpenAI key is a clean no-op" describes the
    CLI's success-exit posture; the API surface instead mirrors the existing "feature
    unavailable" precedent: `api/app.py`'s `_postgres_unavailable_handler` (503, static safe
    message) and `chat_with_repo`'s "The assistant is temporarily unavailable." (503)).
  - otherwise calls `service.backfill(repository_id)` synchronously and returns its
    `embedded`/`already_present`/`failed` counts directly in the response body.

### Async-vs-sync decision (and why)

Chose a **synchronous** POST response instead of the analyze/regenerate background-thread +
progress-dict + status-poll pattern, even though that pattern is the dominant shape for
existing cost operations in this file. Reasoning:
- The task brief for this endpoint says the response must "surface the `EmbeddingBackfillResult`
  counts" — a background-triggered endpoint can only report `running=True` at POST time, never
  final counts; a synchronous call is the only shape that satisfies that requirement directly.
- The CLI (batch 146) already calls `service.backfill(repository_id)` synchronously with no
  progress polling — the API mirrors the same call shape as its sibling surface.
- Spec 027's own open question #4 notes "embedding calls are cheaper per call than analysis
  calls," and the item count is bounded by *already-analyzed* evidence (never the full unanalyzed
  commit history `analyze` walks), so the operation is smaller in expected size/duration than
  `analyze`, weakening the case for background execution.
- If a truly large backfill ever makes this too slow for a synchronous HTTP response, the
  background-progress pattern is still available to retrofit later without changing the route
  path — noted here rather than speculatively building unused progress-dict plumbing now.

### Unavailable-key response shape (and precedent)

503 with a static, non-secret detail message. Precedent: `api/app.py`'s
`_postgres_unavailable_handler` (503, static message, raw exception logged server-side by type
name only — never surfaced) and `chat_with_repo`/`chat_stream_with_repo`'s 503 "The assistant is
temporarily unavailable." for a failed chat call. This is the established "feature currently
cannot do what you asked" posture in this codebase, distinct from a 404 (resource doesn't
exist) or a 422 (bad request shape) — no `OPENAI_API_KEY` is neither.

### Real symbols grounded on

- `build_embedding_backfill_service(*, project_root: Path) -> EmbeddingBackfillService`
  (`composition.py`, batch 145) — always returns a service instance; its `is_available` property
  (added as a follow-up fix in batch 146) is `False` without an embedder.
- `EmbeddingBackfillService.estimate_backfill_calls(repository_id) -> int` and
  `.backfill(repository_id) -> EmbeddingBackfillResult` (`application/embedding_backfill_service.py`).
- `EmbeddingBackfillResult` dataclass fields: `embedded`, `already_present`, `failed`.
- `_require_repository_exists(repository_id, project_root)` — the shared 404 gate already used
  by `get_patterns`, `get_commits`, `estimate_analyze`, `delete_repo`.
- `require_api_key` (`api/auth.py`) — the same bearer-token dependency used by
  `trigger_analyze`, `delete_repo`, `regenerate_case_study`, `ingest_repo`.
- `limiter` (`api/limiter.py`, slowapi) — `@limiter.limit(...)` decorator pattern from
  `estimate_analyze` (20/minute) and `trigger_analyze` (10/minute), reused verbatim.

### Tests added

New file `tests/unit/test_api_backfill.py` (10 tests), mirroring `test_api_analyze.py`'s
fixture style (temp SQLite DB with only the `ingestion_runs` table needed by the existence
gate) and its `monkeypatch.setattr(repos_module, "build_X", ...)` injection technique. A
hand-rolled `_FakeBackfillService` (controllable `is_available`, `estimate_backfill_calls`,
`backfill`) is injected via `build_embedding_backfill_service` — no real embedder, no
network/LLM calls, no need to seed `commit_analyses`/`discussion_evidence`/`embedding_vectors`
tables (the service's own missing-set logic is already covered by
`test_embedding_backfill_service.py`; these tests exercise only the route's gating, wiring, and
response shape):

- `test_status_returns_404_when_db_missing`
- `test_status_returns_404_for_unknown_repository`
- `test_status_available_false_and_missing_zero_without_key`
- `test_status_available_true_reports_missing_count`
- `test_run_returns_404_when_db_missing`
- `test_run_returns_404_for_unknown_repository`
- `test_run_performs_backfill_and_returns_counts`
- `test_run_returns_honest_unavailable_response_without_key`
- `test_run_requires_auth_when_api_key_set`
- `test_run_accepts_valid_auth`

RED confirmed first: 6 of 10 failed before implementation — 4 with `AttributeError:
<module 'git_it.api.routes.repos'> has no attribute 'build_embedding_backfill_service'` (auth
and run tests that patch the not-yet-imported symbol) and 2 with `assert 404 == 401` /
similar wrong-status assertions (the endpoint didn't exist yet, so the 404 came from FastAPI's
own unmatched-route handling rather than the intended `_require_repository_exists` gate). All
10 GREEN after implementing the schemas and routes.

Full suite: **1136 passed, 33 skipped** (was 1117 passed / 33 skipped after batch 146; +10 new
tests from this batch, +9 from an unrelated concurrent human change to
`tests/unit/test_api_static.py`, no regressions).

Gates: `ruff check .` clean, `ruff format --check .` clean (one line in `repos.py` needed
`ruff format` applied for the two-line `@router.get(...)` decorator wrap), `mypy src/` clean
(90 source files, no issues), full `pytest -q --no-cov` green.

### Gotchas

- Did not touch `src/git_it/static/` or `tests/unit/test_api_static.py` — the dashboard button
  is out of scope here (batch 148) and the static test file had uncommitted human changes per
  the batch brief.
- Did not touch `interfaces/cli.py` or its tests — the CLI command shipped in batch 146.
- Kept both endpoints gated by `_require_repository_exists` (not just `database_is_provisioned`,
  which is what `trigger_analyze` alone uses on its POST) for consistency with the "unknown
  repository" 404 requirement explicit in this batch's test list, and because a POST to
  `backfill-embeddings` for a repository that was never ingested has no analyses/evidence to act
  on either way.
- The GET/POST pair shares one path (`/backfill-embeddings`) rather than the
  `analyze` / `analyze/estimate` two-path split — chosen because this batch's brief explicitly
  named this shape, it reads naturally as "GET the status of / POST to this resource," and there
  is no separate progress-poll route needed given the synchronous POST design above.

### Commits

(left uncommitted — orchestrator reviews, runs gates, and commits)
