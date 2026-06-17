## Batch 44 — Pattern enrichment with evidence, time range, and confidence

### Goal

Enrich every detected pattern with three new fields required by spec 003: evidence commit SHAs (which commits triggered the pattern), time range (earliest/latest committed_at among evidence commits), and a deterministic confidence score.

### Examples covered

```text
Hotspots (files with ≥5 commits):
  src/auth.py: 42 commits, churn 8,234  [confidence: 1.00]
    Evidence: a1b2c3d, e4f5g6h, ...
    Period: 2024-01-15 → 2026-06-01
```

### Tests added

- `tests/unit/test_pattern_enrichment.py` — 10 new tests (confidence formulas, evidence SHAs, time_range derivation, defaults when readers absent)
- `tests/unit/test_sqlite_file_evidence.py` — 3 SQLite integration tests (top-N evidence commits, limit param, date map)
- New tests added to `test_pattern_detection_service.py`

### Production behavior added

- `domain/patterns.py` — all 6 pattern dataclasses gain `evidence_commit_shas: tuple[str, ...] = ()`, `time_range: tuple[str, str] | None = None`, `confidence: float = 0.0`
- `infrastructure/sqlite.py` — `SqliteCommitReader.get_commit_date_map()` returns `{sha: committed_at}`; `SqliteFileFactReader.get_file_evidence_commits()` returns top-N most-recent SHAs per file
- `application/ports.py` — `CommitDateReader` and `FileEvidenceReader` protocols added
- `application/pattern_detection_service.py` — two new optional constructor params; `detect()` pre-fetches both maps; each sub-detector computes evidence + time_range + confidence
- `interfaces/cli.py` — `_print_pattern_report` shows confidence %, 7-char abbreviated SHAs, and period
- `composition.py` — wired new readers

### Confidence formulas

| Pattern | Formula |
|---|---|
| Hotspot | `min(1.0, commit_count / 20)` |
| BugfixRecurrence | `min(1.0, bugfix_commit_count / 10)` |
| RefactorWave | `min(1.0, refactor_ratio * 2.0)` |
| TestGrowthSignal | `min(1.0, test_to_bugfix_ratio / 2.0)` |
| RevertSignal | `min(1.0, revert_ratio * 5.0)` |
| OwnershipConcentration | `1.0 - min(1.0, (author_count - 1) / 5.0)` |

### Commits

- `b97091c feat: add evidence, time_range, confidence fields to pattern domain models`
- `dab5064 feat: add file evidence and commit date readers to sqlite infrastructure`
- `9092f27 feat: wire evidence enrichment into pattern detection service`

---
