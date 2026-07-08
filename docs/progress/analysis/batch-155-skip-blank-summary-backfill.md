## Batch 155 — Skip non-embeddable blank-summary items in embedding backfill count

### Goal

Stop `EmbeddingBackfillService` from counting (and re-attempting to embed) items whose
summary text is blank or whitespace-only. Such items can never be embedded, so they were
reported as permanently "missing", making the dashboard's "Enable semantic search (N)"
button reappear with the same N after every backfill.

### Why

Confirmed in production: backfill status permanently reported `missing: 2`, which were 2
`discussion_evidence` rows with blank summaries. The live embedder (`EmbeddingService`)
embeds `analysis.summary` / `evidence.summary` and returns `None` for empty input, so a
blank-summary row is structurally non-embeddable — it never leaves the "missing" set, and
`estimate_backfill_calls` kept returning a non-zero count that the dashboard surfaced
forever.

### What was added

**`src/git_it/repository_ingestion/application/embedding_backfill_service.py`**
- In `_missing_items`, blank/whitespace-only summaries are now excluded from the candidate
  lists *before* missing/already-present are computed:
  - `analyses = [a for a in ...list_analyses(...) if (a.summary or "").strip()]`
  - `evidence = [i for i in ...get_discussion_evidence(...) if (i.summary or "").strip()]`
- Added a comment explaining WHY (blank-summary items are structurally non-embeddable;
  counting them as "missing" made the button reappear forever).
- Everything else is unchanged. The per-item failure isolation and safe
  `type(exc).__name__`-only logging posture were left exactly as they were — no raw
  exceptions or embedded content are logged.

Because `_missing_items` feeds both `estimate_backfill_calls` and `backfill`, the estimate
and the embed pass now agree: a blank-summary item is neither counted nor sent to the
embedder.

### Tests added

`tests/unit/test_embedding_backfill_service.py` (2 new tests, RED first, confirmed failing
with `assert 2 == 1` before the fix, GREEN after):
- `test_blank_summary_commit_analysis_is_not_counted_or_embedded` — a commit analysis with
  a whitespace-only summary is excluded from `estimate_backfill_calls` and never passed to
  the embedder during `backfill()`, while a sibling analysis with a real summary is
  embedded. Asserts the embedder spy recorded only the real SHA.
- `test_blank_summary_discussion_evidence_is_not_counted_or_embedded` — same for a
  discussion evidence item with a blank summary. Asserts only the non-blank evidence URL
  reached the embedder.

Full suite: **1173 passed, 33 skipped** (+2 new tests, no regressions).

### Gotchas

- `DiscussionEvidence.discussion_url` is validated against
  `https://github.com/{owner}/{repo}/discussions/{number}` (numeric id required), so the
  blank-summary evidence fixture uses a numeric discussion URL (`.../discussions/1`) — only
  the `summary` is blank, not the URL.
- The `_FakeEmbedder` test double already records `commit_calls` / `evidence_calls`, so
  asserting the blank item was skipped needed no new test infrastructure.

### Commits

- `fix: skip non-embeddable blank-summary items in embedding backfill count`
