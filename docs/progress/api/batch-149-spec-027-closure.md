## Batch 149 — Spec 027 closure (embedding backfill)

### Goal

Close spec 027 (Embedding Backfill for Previously-Analyzed Evidence) now that all four
implementation slices are shipped: mark the spec `Implemented`, update the roadmap, and correct
the README notes that still told users old analyses could not be backfilled.

### What was added

- `docs/specs/027-embedding-backfill.md`: status `Draft` → `Implemented`.
- `docs/architecture.md`: the Roadmap entry for spec 027 now records it as implemented across
  batches 145–148 (service, CLI, API endpoints, dashboard button) instead of "Not yet built".
- `README.md`: the two backfill notes ("Everyday use" and "Troubleshooting") no longer say old
  analyses are never backfilled — they now point at `git-it backfill-embeddings <repo>` and the
  **Enable semantic search** dashboard button as the supported way to embed already-analyzed
  evidence after adding `OPENAI_API_KEY`, with no re-analysis needed.

### Implementation trail (spec 027)

| Batch | Slice | Commit |
|-------|-------|--------|
| 145 | `EmbeddingBackfillService` (application core, idempotent via the `(repository_id, source_type, source_id)` PK) | `e7f467a` |
| 146 | `git-it backfill-embeddings` CLI + budget guardrail | `dff7af6` |
| — | Fix: no-`OPENAI_API_KEY` CLI message (added `is_available`; the factory always returns a service, so `if service is None` was dead code) | `042f7e2` |
| 147 | `GET`/`POST /api/repos/{id}/backfill-embeddings` (status + synchronous run, 503 without a key) | `2393f8f` |
| 148 | "Enable semantic search" dashboard button (shown only when `available && missing > 0`) | `4c1b57b` |

### Tests / verification

No new production behavior in this batch (docs-only closure). The feature is covered by the
unit/integration tests added in 145–148 (`test_embedding_backfill_service.py`,
`test_backfill_embeddings_cli.py`, `test_api_backfill.py`, `test_api_static_backfill.py`) and by
a live Playwright drive of the button (reveal on `available && missing > 0`, result summary after
POST, auto-hide once `missing` drops to 0). Full suite green at 1142 passed / 33 skipped.

### Gotchas

- The scope-locked decision (from the user) was: backfill both commit analyses AND discussion
  evidence (parity with the live pipeline); releases/advisories are not embedded by anything, so
  they remain out of scope. Idempotency is guaranteed by the embedding store's upsert PK.
- The batch-146 CLI shipped (via a human-made commit while a session limit interrupted the
  sub-agent) with a latent no-key UX bug whose own progress-doc Gotcha described a fix that was
  not actually in the committed code — caught by independent verification and fixed in `042f7e2`.

### Commits

- `docs: close spec 027 (embedding backfill) — mark Implemented, update roadmap and README`
