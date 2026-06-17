## Batch 43 — Parallel async analysis

### Goal

Run multiple LLM calls concurrently instead of sequentially. A new `--concurrency N` flag controls the maximum number of parallel calls. Default is 1 (sequential, same behaviour as before).

### Design

`asyncio.to_thread()` wraps each sync `_analyze_with_client()` call so it runs in the thread pool without changing any Protocol. `asyncio.Semaphore(concurrency)` bounds parallelism. `asyncio.gather()` collects results. The original commit order is reconstructed after gathering by iterating the original `commits` list and looking up cached/analyzed SHAs in maps.

### Examples covered

```text
# Sequential (default)
$ git-it run https://github.com/owner/repo --concurrency 1

# 5 parallel LLM calls
$ git-it analyze-commits https://github.com/owner/repo --concurrency 5
```

### Tests added

- `tests/unit/test_commit_analysis_async.py` — 9 async service tests (same results as sync, concurrency limit enforced via `ConcurrencyTrackingClient`, order preserved, cached/skip bypass, sample routing)
- New `--concurrency` CLI tests in `test_analyze_commits_cli.py` and `test_pipeline_run_command.py`

### Production behavior added

- `application/commit_analysis_service.py` — new `analyze_commits_async()` method (existing sync `analyze_commits()` untouched)
- `interfaces/cli.py` — `CommitBatchService` Protocol gains `async def analyze_commits_async()`; `--concurrency` on `analyze-commits` and `run`; when `N > 1` routes through `asyncio.run(service.analyze_commits_async(...))`

### Gotchas

- `asyncio.to_thread()` returns `Any` — requires explicit type annotation on the awaited result (`analysis: CommitAnalysis = await asyncio.to_thread(...)`)
- `asyncio_mode = auto` in `pytest.ini` means `async def test_...` works without decorators
- `FakeAnalysisCache` must implement the full `CommitAnalysisReader` Protocol (including `list_analyses()`) even if unused in a specific test

### Commits

- `d354915 feat: add analyze_commits_async with semaphore-based concurrency`
- `92a40fb feat: add --concurrency flag to cli`

---
