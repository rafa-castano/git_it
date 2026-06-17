## Bug fix — commit SHA truncation breaking JOIN queries

### Problem

`CommitAnalysisService._build_messages()` sends `commit.sha[:12]` to the LLM. The LLM echoes the 12-char SHA back as `CommitAnalysis.commit_sha`. When stored, `commit_analyses.commit_sha` is 12 chars while `commit_facts.sha` is 40 chars. The `list_analyses_with_dates()` JOIN returns zero rows → "No analyses found" on `case-study`.

### Fix

After the LLM call, override with the authoritative full SHA from the commit record:

```python
analysis = self.analyze_commit(commit)
analysis = analysis.model_copy(update={"commit_sha": commit.sha})
```

### Regression test added

`tests/unit/test_commit_analysis_service.py` — `test_analyze_commits_stores_full_sha_not_llm_sha`

### Commit

`8018a1e fix: override commit_sha with full sha after llm analysis`
