## Batch 143 — Releases/advisories eval and spec 026 closure (closing batch)

Filed under `docs/progress/evals/`, not `analysis/` or `api/` — this batch is
eval-script-plus-docs work, no `src/` changes, mirroring the precedent set by
batch 112 (`docs/progress/evals/batch-112-discussion-evidence-eval-and-adr.md`)
and batch 124 (`docs/progress/evals/batch-124-semantic-search-eval-and-adr.md`),
which closed specs 022 and 023 the same way.

### Goal

Close out spec 026 (GitHub Releases and Security Advisories as Cited
Narrative Evidence) with its remaining deliverable: the eval the spec's
"Evaluation required" section mandates. This is the last batch in the
spec 026 sequence (batches 137-143): domain (137) → fetchers (138) →
summarizers (139) → stores (140) → ingest wiring (141) → narrative
integration (142) → eval + closure (143, this batch). Also fixes a stale
Roadmap section in `docs/architecture.md` (unrelated to spec 026, but
user-requested doc-hygiene work bundled into the same closing batch).

### Why

Spec 026 explicitly deferred the eval to the implementation batch rather
than requiring it upfront (mirroring specs 022/023's own convention). With
the full pipeline live (domain through narrative integration), the eval can
exercise the real `NarrativeService` end-to-end with fixture
`ReleaseEvidence`/`AdvisoryEvidence` fed via stub readers. Separately,
`docs/architecture.md`'s `## Roadmap` section (written at batch 83) still
listed specs 006 and 008 as open Draft specs, but both were formalized/closed
in batches 102 and 98 respectively — `docs/specs/index.md` already marks
both `Implemented`. The Roadmap section had drifted from the source of truth.

### What was added

**`evals/release_advisory_eval.py`** (new, standalone script, mirrors
`evals/discussion_evidence_eval.py`'s bootstrap/argparse/report pattern —
NOT a pytest test, kept out of the deterministic unit suite):

- Fixture: 2 `Release`s (a breaking-change release and a bugfix release) and
  2 `SecurityAdvisory`s (a critical-severity SQL injection advisory and a
  low-severity denial-of-service advisory), each raw field embedding a
  unique sentinel phrase (`ZEBRA-QUUX-SENTINEL...`,
  `PLATYPUS-FOXTROT-SENTINEL...`, `WOMBAT-YANKEE-SENTINEL...`,
  `IGUANA-TANGO-SENTINEL...`) that is never actually summarized — only the
  paired, paraphrased `ReleaseEvidence`/`AdvisoryEvidence` summary is fed to
  the narrative.
- The critical-severity advisory's `AdvisoryEvidence` fixture deliberately
  carries a *low* confidence (`0.35`) summary — severity and confidence are
  independent axes per the spec, and this pairing is what the third check
  below exercises.
- Builds a real `NarrativeService` with `_StubTemporalReader`,
  `_StubPatternService`, `_StubReleaseEvidenceReader`, and
  `_StubAdvisoryEvidenceReader` (satisfying `ReleaseEvidenceReader`/
  `AdvisoryEvidenceReader` structurally, no real DB) plus a real
  `LiteLLMLLMClient`, then calls `service.generate(...)`.
- Four checks:
  1. **`no_raw_text_leakage`** (deterministic) — asserts none of the 4
     sentinel phrases, nor the raw `Release.body`/`SecurityAdvisory.description`
     fields verbatim (defense-in-depth), appear in the generated narrative.
  2. **`citation_completeness`** (deterministic) — same heuristic as
     `discussion_evidence_eval.py`: if a `ReleaseEvidence.summary`/
     `AdvisoryEvidence.summary` appears used (2+ distinctive words present),
     its `release_url`/`advisory_url` must also appear in the output.
  3. **`severity_intact`** (deterministic) — asserts that once the
     critical-severity advisory's evidence appears used in the narrative,
     the word "critical" is still present, i.e. the summary's low (0.35)
     confidence did not silently downgrade or drop the severity label.
  4. **`severity_confidence_independence_qualitative`** (qualitative,
     reported not hard-failed, per the spec's "if hard to make fully
     deterministic, report it qualitatively" guidance) — reports whether
     hedged language also appears in the narrative; informational only,
     since some hedging about exploit specifics is legitimate on its own.
- API-key-gated exactly like `discussion_evidence_eval.py`
  (`_check_api_key(model)` checking the provider-specific env var derived
  from the `--model` string; `anthropic/claude-haiku-4-5-20251001` default).
  `main()` prints a "Skipped" message and exits `0` when the key is absent.

**`evals/README.md`** — new "Release/Advisory evidence eval (spec 026)"
section, mirroring the "Discussion evidence eval (spec 022)" and "Semantic
search eval (spec 023)" sections' exact format: how to run, options,
requires, and a numbered "what it checks" list.

**`docs/specs/index.md`** — spec 026's row changed from `Draft` to
`Implemented` (its own `Status:` header in
`docs/specs/026-releases-and-security-advisories.md` is intentionally left as
`Draft`, matching the established convention from batch 114/134 that a
spec's own header is not retroactively edited after implementation — only
the index tracks real status).

**`docs/architecture.md`** — the `## Roadmap` section's spec 006 (MCP
Strategy) and spec 008 (Repository Deletion) bullets removed; only the
spec 005 (Documentation Engine) bullet remains, since it is the only entry
still genuinely open. Verified against `docs/specs/index.md` before editing:
both 006 and 008 are already `Implemented` there (006 formalized in batch
102, 008 closed in batch 98 with `test_delete_removes_all_data` now present
in `tests/integration/test_repo_lifecycle.py`). Spec 026 is not added to the
Roadmap despite becoming `Implemented` in this same batch — it was never
listed there as an open Draft spec, and it is now closed, so it has no
Roadmap entry either way.

### Verification

- Ran `PYTHONPATH=src uv run python evals/release_advisory_eval.py` with no
  `ANTHROPIC_API_KEY` set in the shell environment: the eval printed
  `Skipped — no model configured for 'anthropic/claude-haiku-4-5-20251001'...`
  and exited `0`, confirming the keyless-skip path works and never
  hard-fails an environment with no LLM configured.

Full unit suite: **1100 passed, 33 skipped** — unchanged, since this batch
adds no pytest tests and touches no `src/` files (eval scripts are
intentionally excluded from the deterministic suite, same posture as
`evals/discussion_evidence_eval.py` and `evals/semantic_search_eval.py`).

Gates: `ruff check .`, `ruff format --check .`, `mypy src/`, and
`mkdocs build --strict` all pass clean.

### Gotchas

- `ruff check` initially flagged one line in `_check_citation_completeness`
  as too long (105 > 100 chars) — wrapped the f-string assignment in
  parentheses to fix; `ruff format` then reformatted a handful of
  multi-line literals for consistency, same as prior eval-authoring batches.
- `evals/release_advisory_eval.py` is not covered by `mypy src/` (the gate
  only scans `src/`) — identical, pre-existing behavior to
  `evals/discussion_evidence_eval.py`/`evals/semantic_search_eval.py`, not a
  new defect.

### Commits

- `docs: add release/advisory eval, close spec 026, fix stale roadmap`
