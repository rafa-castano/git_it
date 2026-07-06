# Feature Spec: 010 — Case Study Audience Availability

## Summary

The case-study audience selector currently gives no indication of which levels have
already been generated and which will trigger a background LLM call (~1 min wait).
This spec adds a machine-readable `available_audiences` list to the case-study API
response so the frontend can label un-generated options before the user clicks them.

---

## Problem

When a user opens the Case Study tab the audience selector shows "Beginner" and
"Expert" without any hint that selecting "Expert" (if not yet generated) will kick
off a multi-minute regeneration.  The "Generating… this may take a minute" message
only appears *after* the user has already clicked, which is too late to set
expectations.

---

## Goals

1. Backend surfaces which audiences are cached for a given repository.
2. API response includes that list without a separate endpoint.
3. Frontend labels un-cached options so users know upfront.

---

## Non-goals

- Live-updating the dropdown during active regeneration (the existing
  `_pollRegenStatus → loadCaseStudy` reload covers this for free).
- Adding new audience levels (only "beginner" and "expert" exist).
- Changing the regeneration flow itself.

---

## Acceptance Criteria

### AC-1 — Store method: `list_available_audiences`

`SqliteCaseStudyStore` gains a method:

```python
def list_available_audiences(self, repository_id: str) -> list[str]:
    """Return sorted list of audience values that have a case study row."""
```

- Returns the distinct audience strings present in `case_studies` for the given
  `repository_id`, sorted alphabetically.
- Returns `[]` when no rows exist.
- Does NOT raise on missing repository — the store is read-only here.

### AC-2 — API response: `available_audiences` field

`GET /api/repos/{repository_id}/case-study` response includes:

```json
{
  "repository_id": "...",
  "narrative": "...",
  "commit_count": 161,
  "hotspot_count": 12,
  "generated_at": "...",
  "available_audiences": ["beginner"]
}
```

- The field lists the audiences that have a cached case study (may include the
  currently requested one and others).
- Schema: `available_audiences: list[str] = []`.
- Backward-compatible: old clients that ignore unknown fields are unaffected.

### AC-3 — Frontend: option labels reflect availability

In `loadCaseStudy` (`app.js`), each `<option>` in the audience `<select>` is
labelled based on whether its value appears in `data.available_audiences`:

| Cached? | Displayed label |
|---------|-----------------|
| Yes     | `Beginner` / `Expert` |
| No      | `Beginner — generates (~1 min)` / `Expert — generates (~1 min)` |

- The `value` attribute remains unchanged (`"beginner"` / `"expert"`) so
  `_setCsAudience` continues to work without modification.
- The hint text must be present in the option's visible text when the audience is
  not yet generated.

---

## Test strategy

### Unit tests (pytest)

- `test_case_study_store_audiences.py` — AC-1:
  - Seed one row (beginner); assert `["beginner"]` returned.
  - Seed two rows (beginner + expert); assert `["beginner", "expert"]`.
  - Empty DB; assert `[]`.
- `test_api_case_study.py` — AC-2:
  - Seed a beginner case study; call the endpoint; assert `available_audiences == ["beginner"]`.
  - (No expert row seeded; assert "expert" is absent from the list.)

### Frontend verification (Playwright)

- Open a repo where only beginner is generated: Expert option label includes
  "generates" before selection.
- After triggering expert generation and reload: both options show plain labels.

---

## Files affected

| File | Change |
|------|--------|
| `src/git_it/repository_ingestion/infrastructure/sqlite.py` | Add `list_available_audiences` method to `SqliteCaseStudyStore` |
| `src/git_it/api/schemas.py` | Add `available_audiences: list[str] = []` to `CaseStudyResponse` |
| `src/git_it/api/routes/repos.py` | Populate `available_audiences` in `get_case_study` |
| `src/git_it/static/app.js` | Update `<option>` label logic in `loadCaseStudy` |
| `tests/unit/test_case_study_store_audiences.py` | New — AC-1 unit tests |
| `tests/unit/test_api_case_study.py` | New — AC-2 API tests |
