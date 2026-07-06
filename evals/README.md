# Git It — Evaluation Harness

## What it measures

Accuracy of the LLM commit classifier against 20 hand-labeled commits.
Two dimensions are scored: **category** (feature, bugfix, refactor, test, docs, chore,
build, security, performance) and **risk level** (low, medium, high).

## How to run

```bash
uv run python evals/run.py
```

Options:

```
--model MODEL     LiteLLM model string  (default: anthropic/claude-haiku-4-5-20251001)
--fixture PATH    Path to golden_commits.json  (default: evals/golden_commits.json)
--output PATH     Write JSON report to this file in addition to stdout
--verbose         Print each commit message and the full predicted analysis
```

Requires `ANTHROPIC_API_KEY` (or the key for whichever provider you select).

## How to add new golden commits

Edit `evals/golden_commits.json` and append an object following this schema:

```json
{
  "sha": "<12-char hex string>",
  "message": "<commit message first line>",
  "author_name": "<Author Name>",
  "committed_at": "<ISO 8601 datetime>",
  "files_changed": ["path/to/file.py"],
  "expected_category": "<one of the CommitCategory enum values>",
  "expected_risk_level": "<low | medium | high>",
  "rationale": "<why this label is correct>"
}
```

Valid categories: `feature`, `bugfix`, `refactor`, `test`, `docs`,
`chore`, `build`, `security`, `performance`, `unknown`.

## Passing score

**75% combined** (average of category accuracy and risk accuracy).
Below 75% indicates model regression or prompt drift and should block a release.

---

## Discussion evidence eval (spec 022)

Checks that case-study narratives generated with GitHub Discussions evidence
respect the evidence-discipline properties `specs/022-github-discussions.md`
requires: citation completeness, no raw-text leakage, and uncertainty
preservation.

### How to run

```bash
uv run python evals/discussion_evidence_eval.py
```

Options:

```
--model MODEL     LiteLLM model string  (default: anthropic/claude-haiku-4-5-20251001)
--verbose         Print the full generated narrative
```

Requires an API key for the selected model (e.g. `ANTHROPIC_API_KEY`). If no key
is configured, the eval prints a "skipped" message and exits `0` — it never
hard-fails an environment with no LLM configured.

### What it checks

1. **Citation completeness** — a practical, non-brittle heuristic: if a
   `DiscussionEvidence.summary` appears to have been used in the narrative
   (several of its distinctive words show up), its `discussion_url` must also
   appear somewhere in the output.
2. **No raw-text leakage** (deterministic, the strongest check) — each fixture
   `Discussion` embeds a unique sentinel phrase in its raw `title`/`body`/
   `answer_body`. The eval asserts none of those sentinel phrases (nor the raw
   fields verbatim, as defense-in-depth) appear anywhere in the generated
   narrative — only the validated `DiscussionEvidence.summary` and
   `discussion_url` may ever reach it. This is the key security property from
   spec 022: raw, untrusted discussion text must never cross into the
   narrative.
3. **Uncertainty preservation** (best-effort/qualitative) — reports whether the
   narrative uses hedged language ("evidence suggests," "may," "appears") near
   the fixture's low-confidence (`0.3`) discussion evidence item. This is a
   qualitative observation per the spec, not a hard pass/fail.

The eval exits non-zero only if the two deterministic checks (no raw-text
leakage, citation completeness) fail; the uncertainty check is reported but
never fails the run.

---

## Semantic search eval (spec 023)

Checks that embedding-based semantic search over `CommitAnalysis`/
`DiscussionEvidence` summaries respects the properties
`specs/023-rag-semantic-commit-search.md` requires: concept recall, no
raw-text leakage, and relevance-ordering sanity.

### How to run

```bash
uv run python evals/semantic_search_eval.py
```

Options:

```
--verbose         Print every similarity result gathered during the eval
```

Requires `OPENAI_API_KEY` specifically — this eval calls
`LiteLLMEmbeddingClient`/`build_embedding_client()` for real embeddings, not
a completions model, so unlike `discussion_evidence_eval.py` it takes no
`--model` argument. If `OPENAI_API_KEY` is not configured, the eval prints a
"skipped" message and exits `0` — it never hard-fails an environment with no
embedding provider configured.

### What it checks

1. **Concept recall** — a fixture set of `CommitAnalysis` summaries covering
   several distinct, clearly-separated concepts (a SQL injection fix, a
   flaky test suite fix, a database migration rollback, an auth token expiry
   bug, and a docs-typo distractor) is embedded via a real embedding call.
   For each of a matching set of natural-language queries — deliberately
   phrased with different vocabulary than the summaries themselves use — the
   eval asserts the known-correct fixture's `evidence_ref` appears within
   the top-`k` `SimilarityResult`s returned by `SemanticSearchService`.
2. **No raw-text leakage** (deterministic, mirrors spec 022's eval) — each
   fixture item's summary is paired with a raw, hypothetical commit-message
   sentinel phrase that is never actually embedded. The eval asserts none of
   those sentinel phrases appear in any `SimilarityResult.summary_text` —
   only the validated summary that was actually embedded may ever surface.
3. **Relevance ordering sanity** — a query closely matching the SQL
   injection summary's wording ("what security mistakes were made early in
   the project") must score higher against that summary than a control
   query about an unrelated concept (documentation typos) does. This is a
   coarse sanity check on the embedding model's usefulness for this corpus,
   not a strict correctness proof.

All three checks in this eval are deterministic given a real embedding
response — the eval exits non-zero if any of them fail (unlike the
discussion-evidence eval, there is no qualitative-only check here).

This eval builds its fixtures and stubs entirely in-process (an in-memory
stand-in satisfying the `EmbeddingReader` protocol) — no database is
touched, and the only real network call is the embedding API itself.
