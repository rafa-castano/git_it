## Batch 40 — Chronological ordering and date filters

### Goal

Allow users to analyze commits from oldest to newest (`--order oldest`) and filter by date range (`--since`, `--until`).

### Source of truth

- UX improvement: "follow the repo from day 1"

### Examples covered

```text
$ git-it run https://github.com/owner/repo --order oldest --limit 20
$ git-it analyze-commits https://github.com/owner/repo --since 2024-01-01 --until 2024-06-30
$ git-it commits https://github.com/owner/repo --order oldest
```

### Tests added

- `tests/unit/test_sqlite_commit_reader_ordering.py` — 10 tests
- `tests/unit/test_commit_analysis_ordering.py` — 6 tests
- New ordering/date tests in CLI test files

### Production behavior added

- `application/commit_query_service.py` — `CommitReader` Protocol and `RepositoryCommitQueryService` extended with `order: str = "newest"`, `since: str | None = None`, `until: str | None = None`
- `infrastructure/sqlite.py` — conditional `WHERE substr(committed_at, 1, 10) >= ?` / `<= ?` and dynamic `ORDER BY committed_at ASC/DESC`
- `application/commit_analysis_service.py` — `analyze_commits` and `estimate_llm_calls` forward the new params
- `interfaces/cli.py` — `--order`, `--since`, `--until` on `commits`, `analyze-commits`, `run`; Protocol updates

### Gotcha

Use `str` (not `Literal["newest", "oldest"]`) in Protocol method signatures. mypy enforces parameter contravariance — a narrower Literal type on the concrete class causes Protocol violations.

### Commits

- `458d7b0 feat: add order, since, until to commit reader and sqlite`
- `ff67273 feat: wire order, since, until through service and cli`

---
