## Batch 154 — Spec 028 closure (refresh all repositories)

### Goal

Close spec 028 (Refresh All Repositories — Fetch New Commits Without Re-Pasting the URL) now
that all four implementation slices are shipped: mark the spec `Implemented`, update the roadmap,
and add the "Refresh all" flow to the README so users know about the batch alternative to
re-pasting each repository URL.

### What was added

- `docs/specs/028-refresh-all-repositories.md`: status `Draft` → `Implemented`.
- `docs/architecture.md`: the Roadmap entry for spec 028 now records it as implemented across
  batches 150–153 (service, CLI, API endpoint, dashboard button) instead of "Not yet built".
- `README.md`: the "Add new commits from GitHub" note in *Everyday use* now points at the
  **Refresh all** home-page button and the `git-it refresh-all` CLI command as the way to fetch
  new commits for every tracked repository at once — free (no LLM calls), with new commits landing
  unanalyzed and ready for **+ Analyze**.

### Implementation trail (spec 028)

| Batch | Slice | Commit |
|-------|-------|--------|
| 150 | `RefreshAllService` (application core; calls `RepositoryIngestionService.ingest` only — the free fetch+extract path, never any analysis/summarizer collaborator) | `e01c946` |
| 151 | `git-it refresh-all` CLI command (no positional arg; per-repository totals + failure isolation) | `6f010ac` |
| 152 | `POST /api/repos/refresh-all` endpoint (rate-limited, `require_api_key`, DB-not-provisioned → zeroed 200) | `3043185` |
| 153 | "Refresh all" home dashboard button (summary built from numeric fields via `textContent`; re-renders repo cards after) | `f431939` |

### Tests / verification

No new production behavior in this batch (docs-only closure). The feature is covered by the
unit tests added in 150–153 (`test_refresh_all_service.py`, `test_refresh_all_cli.py`,
`test_api_refresh_all.py`, `test_api_static_refresh.py`). Full suite was green at the time each
slice landed.

### Gotchas

- The scope-locked decision (from the user) was **commits only, free**: refresh calls
  `svc.ingest()` directly and bypasses `_ingest_bg`'s paid summarizers (discussion / release /
  advisory evidence). This is enforced *by construction* — `RefreshAllService` has no path to an
  analysis-shaped collaborator, and `test_refresh_all_never_invokes_any_analysis_collaborator`
  guards it with a spy whose `analyze_commits` raises if ever touched.
- Only `IngestionResult.status == "COMPLETED"` counts as a refreshed repo; every other status is
  treated as a failure that is isolated (logged, per-repo `failed` status) so one repository's
  fetch error never aborts the batch. The failure branch scrubs the message (type-name only) to
  avoid leaking tokens present in exception text.
- No APScheduler / no background scheduling — the user explicitly narrowed the original request to
  the manual "Refresh all" action only.

### Commits

- `docs: close spec 028 (refresh all repositories) — mark Implemented, update roadmap and README`
