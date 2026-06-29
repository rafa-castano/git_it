# Batch 75 — Pattern mapper extraction and routes decomposition

## Goal

Reduce `src/git_it/api/routes/repos.py` from 620 lines by extracting the 141-line
domain→schema mapping block out of `get_patterns()` into a dedicated mapper module,
and evaluate whether further splitting the routes file into sub-modules was worthwhile.

## Changes Made

### Step 1 — Extract pattern mapper (mandatory)

Created `src/git_it/api/mappers.py` with a single pure function:

```python
def map_pattern_report(report: PatternReport) -> PatternReportResponse: ...
```

This function encapsulates all list comprehensions and field-by-field schema
construction that were previously inlined inside the `get_patterns()` route handler.
The mapping logic is unchanged; only its location moved.

`get_patterns()` in `repos.py` now delegates to the mapper in three lines:

```python
service = build_pattern_detection_service(project_root=project_root)
report = service.detect(repository_id, hotspot_threshold=hotspot_threshold)
return map_pattern_report(report)
```

Ten schema imports that were only used by the inline mapping were removed from
`repos.py`; they are now imported by `mappers.py` instead.

### Step 2 — Route splitting (skipped)

The routes file has seven logical groups (ingest, repos list, case study + regen,
patterns, commits, estimate + analyze + status, contributors) but many shared
helpers and in-memory state (`_get_db_path`, `_canonical_repo_id`,
`_analyze_progress*`, `_regen_progress*`). Splitting would require a `_common.py`
shared module to avoid circular imports, adding indirection without proportional
clarity gain. After the mapper extraction the file is 480 lines — large but still
navigable with the existing section banners.

## Files Changed

| File | Before | After |
|------|--------|-------|
| `src/git_it/api/routes/repos.py` | 620 lines | 480 lines |
| `src/git_it/api/mappers.py` | — (new) | 151 lines |

## Tests Added

No new tests. This is a pure refactor — all domain objects, schemas, and API
behaviour are identical. Existing 576 unit tests remain green.

## Gotchas

- `PatternReportResponse` is still imported by `repos.py` because it is used as the
  `response_model` argument in the route decorator — the mapper import alone is not
  sufficient.
- The ten schema types that were removed from `repos.py`'s imports are all
  consumed exclusively by `map_pattern_report`; no other route handler referenced
  them.
