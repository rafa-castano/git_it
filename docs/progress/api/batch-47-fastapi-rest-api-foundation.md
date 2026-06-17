## Batch 47 — FastAPI REST API foundation

### Goal

Add a read-only REST API using FastAPI that exposes existing analysis results from SQLite. The API reads from the database — no new analysis is triggered (that stays in the CLI). A `git-it serve` command starts the server.

### Endpoints

```
GET /api/repos                              → list all ingested repositories
GET /api/repos/{id}/case-study             → Markdown narrative + metadata
GET /api/repos/{id}/patterns               → full PatternReport as JSON
GET /api/repos/{id}/commits?limit&order    → paginated commit list with analysis
```

### Tests added

- `tests/unit/test_api_repos.py` — 12 API tests (empty list, repo with data, case-study 404, patterns, paginated commits, ordering)
- `tests/unit/test_serve_command.py` — 4 CLI serve tests

### Production behavior added

- `src/git_it/api/__init__.py` — new package
- `src/git_it/api/app.py` — `create_app(project_root=None)` factory + module-level `app` for uvicorn
- `src/git_it/api/deps.py` — `get_project_root(request)` checks `app.state.project_root` → `GIT_IT_DATA_DIR` env var → `Path.cwd()`
- `src/git_it/api/schemas.py` — Pydantic v2 response models (`RepoListResponse`, `CaseStudyResponse`, `CommitsResponse`, `PatternReportResponse`)
- `src/git_it/api/routes/repos.py` — all 4 endpoints; patterns uses `build_pattern_detection_service(model=None)`; commits LEFT JOIN with commit_analyses
- `interfaces/cli.py` — `serve` subparser with `--host`/`--port`; `_run_serve()` sets `GIT_IT_DATA_DIR` and calls `uvicorn.run`

### Gotcha

`os.environ.setdefault` in `_run_serve` caused test pollution (env var leaked between tests). Fixed with direct assignment + `finally` cleanup in tests.

### Commits

- `588bdbf feat: add FastAPI app with read-only REST API for repos, case studies, patterns, and commits`
- `cbef550 feat: add git-it serve command to launch API server`

---
