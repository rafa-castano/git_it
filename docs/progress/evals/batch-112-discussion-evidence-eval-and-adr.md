## Batch 112 — Discussion evidence eval and ADR 015 (spec 022, closing slice)

### Goal

Close out spec 022 (GitHub Discussions ingestion and narrative evidence) with
its two remaining deliverables: the eval the spec's "Evaluation required"
section mandates, and the follow-up ADR the spec's "ADR impact" section
deferred to the build batch. This is the last batch in the spec 022 sequence
(batches 107-112): domain/stores (107) → fetcher (108) → summarizer (109) →
narrative integration (110) → ingest wiring (111) → eval + ADR (112, this
batch).

### Why

Spec 022 explicitly deferred both the eval and the ADR to the build batch
rather than requiring them upfront. With ingestion, summarization, storage,
and narrative integration all live (batch 111), the pipeline can now be
exercised end-to-end for evaluation purposes, and the two ADR-worthy decisions
(a second GitHub API surface; a second LLM call site whose sole input is
untrusted community text) are now implemented, not merely proposed — so the
ADR can record what was actually built.

### What was added

**`evals/discussion_evidence_eval.py`** (new, standalone script, mirrors
`evals/run.py`'s bootstrap/argparse/report pattern — NOT a pytest test, kept
out of the deterministic unit suite):
- Fixture: 3 raw `Discussion` objects, each carrying a unique sentinel phrase
  (`ZEBRA-QUUX-SENTINEL...`, `PLATYPUS-FOXTROT-SENTINEL...`,
  `WOMBAT-YANKEE-SENTINEL...`) embedded directly in `title`/`body`/
  `answer_body`, plus a matching `list[DiscussionEvidence]` (one item at
  `confidence=0.3` for the uncertainty check), plus two `TimestampedAnalysis`
  commit fixtures so the narrative also has commit content.
- Builds a real `NarrativeService` with stub `temporal_reader`, stub
  `pattern_service` (returns an empty `PatternReport`), stub `discussion_reader`
  (returns the fixture evidence), and a real `LiteLLMLLMClient(model=...)`.
  Calls `.generate(repository_id, force=True)`.
- Three checks:
  1. **No raw-text leakage** (deterministic, the strongest check) — asserts
     none of the three sentinel phrases, nor any whole raw `title`/`body`/
     `answer_body` string (defense-in-depth), appear in the generated
     narrative. This is the check that exits the eval non-zero on failure.
  2. **Citation completeness** (heuristic) — for each `DiscussionEvidence`
     whose summary appears to have been used (≥2 distinctive words from the
     summary present in the narrative), its `discussion_url` must also be
     present. Also exits non-zero on failure.
  3. **Uncertainty preservation** (qualitative, per spec 022's own wording —
     "may start as a manual/qualitative check") — reports whether hedged
     language ("evidence suggests", "may", "appears", "unconfirmed", "rumor",
     etc.) appears in the narrative. Never fails the run.
- API-key-gated like `run.py`: `_check_api_key()` returns `False` (rather than
  exiting) when the required env var for the selected model's provider is
  absent, and `main()` prints a "Skipped" message and exits `0` — this eval
  must never hard-fail an environment with no LLM configured.

**`evals/README.md`** — new "Discussion evidence eval (spec 022)" section:
how to run, what each of the three checks does, and the exit-code contract.

**`docs/adr/015-graphql-discussions-and-untrusted-text-summarization.md`** (new):
records both decisions spec 022 flagged as ADR-worthy:
1. GraphQL is used only where REST is insufficient (Discussions); REST stays
   the default (references ADR 007, and the fixed-template/no-injection
   property of the GraphQL query already documented in the spec).
2. `DiscussionSummarizer`'s security posture for untrusted text as *direct*
   LLM input (as opposed to Git It's own derived analyses, one level removed):
   the per-discussion security preamble, the URL/id trust boundary
   (`discussion_url` sourced from the trusted `Discussion`/GitHub API, never
   from LLM output), schema validation of every `DiscussionEvidence`, and the
   raw-text-never-persisted/logged/rendered guarantee (references ADR 008 and
   ADR 004).

**`docs/adr/index.md`** — new row for ADR 015.

### Verification

- Ran the eval with `ANTHROPIC_API_KEY` unset: prints "Skipped — no model
  configured..." and exits `0`.
- Manually monkeypatched `LiteLLMLLMClient.complete` (no real network call) to
  confirm the full stub-wired `NarrativeService` pipeline produces a narrative
  and that:
  - the no-raw-text-leakage check passes on a clean narrative and correctly
    flips to `False` once a sentinel phrase is appended to the narrative
    (proving the check is not vacuously true);
  - the citation-completeness check passes when every used evidence item's URL
    is present;
  - the uncertainty check reports the hedged phrases found near the
    low-confidence item.
- No real LLM call was made in this sandboxed environment (no API key
  available) — the eval's happy path with a live model was not exercised here,
  only its skip path and its check logic (via the monkeypatch above).

Full unit suite: **873 passed, 21 skipped** — unchanged from batch 111, since
this batch adds no pytest tests (eval scripts are intentionally excluded from
the deterministic suite per CODEX.md's LLM-output-is-not-unit-testable
posture).

Gates: `ruff check .`, `ruff format --check .`, `mypy src/` all pass clean.

### Gotchas

- An earlier draft of the no-raw-text-leakage check compared whole raw
  `title`/`body`/`answer_body` strings against the narrative. That is too weak
  a check in practice — an LLM never reproduces an entire raw field verbatim,
  so the check would trivially "pass" even if a fragment of raw text leaked.
  Fixed by embedding a unique sentinel phrase in each fixture discussion's raw
  text and asserting that exact phrase never appears in the narrative — a
  precise, deterministic proxy for "no raw discussion text reached the LLM
  output," verified by a leak-injection test during development.
- `evals/discussion_evidence_eval.py` is not covered by `mypy src/` (the gate
  only scans `src/`), but `ruff check .`/`ruff format --check .` do scan the
  repo root, so the eval script was linted and formatted like any other
  tracked Python file.

### Commits

- `test: add discussion-evidence eval and ADR 015 for spec 022`
