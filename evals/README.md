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
