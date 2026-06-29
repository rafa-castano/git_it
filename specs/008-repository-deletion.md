# Feature Spec: Repository Deletion

**Status:** Draft
**Spec number:** 008
**Author:** Rafael Castaño
**Date:** 2026-06-29

---

## Summary

Allow users to permanently delete a saved repository and all its associated data (commits,
analyses, case studies, synopsis, ingestion runs) from two locations: the home page repo card
and the sidebar of the repository detail page. Deletion requires an explicit confirmation step
and is blocked when an ingest or analysis operation is in progress.

---

## Problem

Once a repository is added to git_it there is no way to remove it. Users experimenting with
multiple repos accumulate stale entries with no recourse. There is no "undo" mechanism, so
deletion must be intentional and confirmed.

---

## Goals

1. Expose a `DELETE /api/repos/{repository_id}` endpoint that hard-deletes the repo and all
   its data, protected by API key and a 10/minute rate limit.
2. Return `409 Conflict` if an ingest or analysis operation is currently running for that repo.
3. Add a Delete button to each repo card on the home page.
4. Add a Delete button to the repository sidebar on the repo detail page.
5. Show a confirmation modal before executing the delete in both UI locations.
6. After a successful delete from the repo detail page, redirect the user to the home page.

---

## Non-goals

- Soft delete / archive (marking a repo as hidden but keeping data).
- Selective deletion (keeping commits while removing analyses).
- Stopping an in-progress operation before deletion (the user must wait or the operation must
  finish naturally).
- Batch deletion of multiple repos in one action.
- Undo / restore after deletion.

---

## Users

All users of the git_it local-first UI. No distinct user roles exist.

---

## User stories

1. **As a user on the home page**, I want to delete a repository I no longer need so that the
   list stays clean.
2. **As a user on the repo detail page**, I want to delete the current repository without
   navigating back to the home page first.
3. **As a user**, I want a confirmation step before deletion so I don't lose data accidentally.
4. **As a user**, I want to be clearly informed if deletion is blocked because an operation is
   in progress.

---

## Acceptance criteria

```gherkin
Feature: Repository Deletion

  Background:
    Given the API is running
    And at least one repository has been ingested

  # --- API ---

  Scenario: Successful hard delete via API
    Given no ingest or analysis is running for the repository
    When the client sends DELETE /api/repos/{repository_id} with a valid API key
    Then the response status is 200
    And the repository no longer appears in GET /api/repos
    And GET /api/repos/{repository_id}/commits returns 404
    And GET /api/repos/{repository_id}/patterns returns 404
    And GET /api/repos/{repository_id}/analyze/estimate returns 404

  Scenario: DELETE blocked when analysis is in progress
    Given an analysis operation is currently running for the repository
    When the client sends DELETE /api/repos/{repository_id} with a valid API key
    Then the response status is 409
    And the response body contains a human-readable reason ("operation in progress")
    And the repository still appears in GET /api/repos

  Scenario: DELETE blocked when ingest is in progress
    Given an ingest operation is currently running for the repository
    When the client sends DELETE /api/repos/{repository_id} with a valid API key
    Then the response status is 409

  Scenario: DELETE on unknown repository returns 404
    When the client sends DELETE /api/repos/nonexistent-id with a valid API key
    Then the response status is 404

  Scenario: DELETE without API key returns 401
    When the client sends DELETE /api/repos/{repository_id} without an API key header
    Then the response status is 401

  Scenario: DELETE is rate-limited
    Given the endpoint allows 10 requests per minute
    When the endpoint configuration is inspected
    Then the @limiter.limit("10/minute") decorator is registered for the delete handler

  # --- UI: Home page ---

  Scenario: Delete button visible on home page card
    Given the home page is loaded with at least one repository
    Then each repository card has a Delete button

  Scenario: Clicking Delete on home card shows confirmation modal
    When the user clicks the Delete button on a repository card
    Then a confirmation modal appears
    And the modal identifies the repository (URL or name)
    And the modal has a "Confirm" / "Cancel" choice

  Scenario: Cancelling confirmation leaves repo intact
    When the user clicks Delete, then clicks Cancel in the modal
    Then the modal closes
    And the repository card is still visible

  Scenario: Confirming deletion removes the card
    When the user clicks Delete, then clicks Confirm
    Then the DELETE API call is made
    And the repository card disappears from the home page
    And no page reload is required

  Scenario: Delete blocked during in-progress operation (home page)
    Given an ingest or analysis is running (repo status shows progress)
    When the user clicks Delete and confirms
    Then an error message is shown (e.g. "Cannot delete: operation in progress")
    And the card remains visible

  # --- UI: Repo detail page ---

  Scenario: Delete button visible in repo sidebar
    Given the user is on the repo detail page
    Then the sidebar contains a Delete button (styled as a destructive action)

  Scenario: Confirming deletion from repo page redirects to home
    When the user confirms deletion from the repo detail page
    Then the DELETE API call is made
    And the user is redirected to the home page
    And the deleted repo no longer appears in the list
```

---

## Domain concepts

- **Hard delete**: permanent removal of all rows in every table that reference the
  `repository_id`. No soft-delete flag; the repository is gone.
- **In-progress guard**: the in-memory dicts `_analyze_progress` and `_regen_progress` in
  `routes/repos.py` track running operations. If either has `running: True` for the repo, the
  delete is blocked.
- **API key auth**: the `require_api_key` FastAPI dependency already used by write endpoints
  (ingest, analyze, regen) must also guard the delete endpoint.

---

## Inputs and outputs

### `DELETE /api/repos/{repository_id}`

**Request headers:** `X-API-Key: <key>` (same key used for other write operations)

**Response 200:**
```json
{ "deleted": true, "repository_id": "<id>" }
```

**Response 404:** repository not found.

**Response 409:**
```json
{ "detail": "Cannot delete repository while an operation is in progress." }
```

**Response 401:** missing or invalid API key.

---

## Evidence requirements

- All data deletion is verified by querying the affected endpoints after delete and asserting
  404 responses.
- In-progress guard is tested by simulating `_analyze_progress[repo_id] = {"running": True, ...}`
  before calling DELETE and asserting 409.
- Rate-limit registration is tested via slowapi introspection (same pattern as batch 73 test
  for `estimate_analyze`).

---

## Failure modes

| Failure | Expected behavior |
|---------|------------------|
| Repo not found | 404 |
| Operation in progress | 409 with reason |
| API key missing | 401 |
| DB error during delete | 500; partial deletion is acceptable for MVP (no transaction rollback required) |
| Network error during UI delete call | Error toast shown; card remains visible |

---

## Security considerations

- `DELETE` is a destructive write operation → **must** require `require_api_key`.
- Rate limit at 10/minute prevents abuse (consistent with ingest/analyze limits).
- The `repository_id` is validated against the DB; SQL must use parameterised queries
  (already the convention across all adapters).
- Repo text (URLs, commit messages) in the modal is escaped; no raw HTML injection.

---

## Privacy considerations

Deletion permanently removes all user-provided data for that repository. No retention or
logging of deleted content is required for this MVP.

---

## Observability

No new telemetry for MVP. The 404 on subsequent calls is sufficient evidence of successful
deletion.

---

## Tests required

### Unit tests (new)

1. `test_delete_repo_success` — asserts 200 and that subsequent GET calls return 404.
2. `test_delete_repo_not_found` — asserts 404 when `repository_id` is unknown.
3. `test_delete_repo_requires_api_key` — asserts 401 without key.
4. `test_delete_repo_blocked_when_analysis_running` — sets `_analyze_progress[id] = {"running": True, ...}` and asserts 409.
5. `test_delete_repo_blocked_when_regen_running` — sets `_regen_progress[id] = {"running": True, ...}` and asserts 409.
6. `test_delete_repo_is_rate_limited_at_10_per_minute` — slowapi introspection (same pattern as batch 73).

### Integration tests (optional but recommended)

Extend `tests/integration/test_repo_lifecycle.py` with `test_delete_removes_all_data`:
POST ingest → DELETE → assert all sub-endpoints return 404.

### TDD order

Red → Green → Refactor for each unit test listed above.

---

## Evaluation required

None beyond automated tests. No LLM output involved.

---

## Documentation impact

- Create `docs/progress/api/batch-78-repository-deletion.md`.
- Add entry to `docs/progress/README.md` (API section).

---

## ADR impact

None. The delete endpoint follows existing patterns (API key, rate limit, in-memory guard).
No new architectural decisions required.

---

## Open questions

None — all decisions resolved:
- Confirmation: yes, modal.
- Data scope: hard delete, all tables.
- In-progress behavior: block with 409.
- Post-delete navigation from repo page: redirect to home.
