## Batch 139 — Release and Advisory summarizers with injection-safe URL/severity boundaries (spec 026, slice 3)

### Goal

Implement `ReleaseSummarizer` and `AdvisorySummarizer`, the application-layer services that
turn each qualifying `Release` and `SecurityAdvisory` (raw, ephemeral, fetched by the
batch-138 REST fetchers) into a single schema-validated `ReleaseEvidence` /
`AdvisoryEvidence` item, one LLM call per item. This is slice 3 of spec 026's build order
(domain → fetchers → summarizers → stores → wiring → narrative); persistence and narrative
integration land in later batches.

### Why

The fetchers (batch 138) produce raw `Release`/`SecurityAdvisory` candidates; nothing yet
turns them into narrative-safe evidence. Both summarizers are additional LLM call sites
whose sole input is untrusted, external, maintainer-authored text — mirroring
`DiscussionSummarizer` (spec 022)'s trust-boundary pattern exactly, extended to two new
evidence shapes.

### What was added

**`application/release_summarizer.py`** (new)
- `ReleaseSummarizer(llm_client: LLMClient, *, model: str)` — same constructor shape as
  `DiscussionSummarizer`.
- `summarize(releases: list[Release]) -> list[ReleaseEvidence]` — exactly one
  `llm_client.complete()` call per release; system prompt carries the same untrusted-data
  security preamble, instructing the model to return only a JSON object with `claim_type`
  (one of `breaking_change`/`feature_release`/`bugfix_release`/`security_release`),
  `summary`, `confidence`, `limitations`.
- User message wraps `tag_name`/`name`/`body` in a `[RELEASE DATA] ... [/RELEASE DATA]`
  untrusted-data envelope.
- **Trust boundary**: `tag_name`, `release_url`, and `source_inputs` on the resulting
  `ReleaseEvidence` are always taken from the trusted `Release` object (`release.tag_name`,
  `release.html_url`), never from the LLM's JSON — the LLM supplies only
  `claim_type`/`summary`/`confidence`/`limitations`.

**`application/advisory_summarizer.py`** (new)
- `AdvisorySummarizer(llm_client: LLMClient, *, model: str)` — same constructor shape.
- `summarize(advisories: list[SecurityAdvisory]) -> list[AdvisoryEvidence]` — the LLM
  produces only `summary`, `confidence`, `limitations` — **no `claim_type` and no
  `severity`**: advisories have no claim_type field, and severity is a trusted, factual
  GitHub API value, never an LLM judgment.
- User message wraps `ghsa_id`/`summary`/`description`/`severity` in a
  `[ADVISORY DATA] ... [/ADVISORY DATA]` envelope (severity is shown as context for the
  summary but is never sourced from the LLM's response).
- **Trust boundary**: `ghsa_id`, `advisory_url`, `severity`, and `source_inputs` on the
  resulting `AdvisoryEvidence` are always taken from the trusted `SecurityAdvisory` object
  (`advisory.ghsa_id`, `advisory.html_url`, `advisory.severity`), never from the LLM's JSON.
- `severity=advisory.severity` needs `# type: ignore[arg-type]` — `SecurityAdvisory.severity`
  is a plain `str` at the domain boundary (set from the raw GitHub API response in
  `infrastructure/github.py`), while `AdvisoryEvidence.severity` is
  `Literal["low", "medium", "high", "critical"]`. Pydantic validates the literal at
  construction time and raises `ValidationError` for anything else, which is caught by the
  same per-item failure-isolation try/except — so an unexpected API value degrades to
  "drop this item," not a crash.

Both files share `DiscussionSummarizer`'s exact structure: `_parse_payload` (strip code
fences, `json.loads`, assert dict, check required keys) and per-item failure isolation
catching `(json.JSONDecodeError, ValidationError, KeyError, TypeError, ValueError)` plus a
broad `except Exception`, logging only `type(exc).__name__` — never raw response bodies or
release/advisory text.

### Tests added

`tests/unit/test_release_summarizer.py` (17 tests) and
`tests/unit/test_advisory_summarizer.py` (17 tests), using a stub `LLMClient` with scripted
per-call responses, mirroring `test_discussion_summarizer.py`'s structure:
- valid JSON response → validated Evidence with LLM-supplied fields plus trusted
  url/id/(severity) from the input object;
- **URL trust-boundary test**: LLM JSON also contains a bogus `release_url`/`advisory_url` —
  asserts the resulting Evidence's URL is the trusted object's `html_url`, not the LLM's
  value;
- **severity trust-boundary test** (advisory only): LLM JSON contains a different
  `severity` — asserts the resulting `AdvisoryEvidence.severity` is the trusted
  `SecurityAdvisory.severity`, not the LLM's value;
- missing required keys / `confidence` out of `[0.0, 1.0]` / invalid `claim_type` → dropped;
- non-JSON response → dropped; markdown code fence wrapping → still parsed;
- malformed `html_url` on the trusted input object → `ReleaseEvidence`/`AdvisoryEvidence`'s
  own URL validator raises `ValidationError`, caught and dropped (not a bug — same behavior
  as `DiscussionSummarizer`);
- one item's `complete()` raising in a batch of three → that one dropped, the other two
  still summarized, in input order;
- exactly one `complete()` call per item; system prompt security preamble check; empty
  input list → zero LLM calls;
- **no-raw-text-leakage guard**: a unique sentinel string embedded in the release
  `body`/advisory `description`, paired with a failing LLM call, asserts (via `caplog`) that
  the sentinel never appears in logs — only the exception type name does (mirrors
  `test_embedding_service.py`'s secret-leak guard style).

Full suite: **1059 passed, 27 skipped** (34 new tests, all in the two new test files).

### Gotchas

- Same URL trust-boundary reconciliation as batch 109 (AGENTS.md's conflict-resolution order
  ranks security constraints above literal AC wording): the LLM never supplies
  `release_url`/`advisory_url`/`severity`; those come only from the trusted fetched object.
  The Pydantic-level URL/severity validators remain defense-in-depth, not the primary
  control.
- `AdvisorySummarizer` needed one `# type: ignore[arg-type]` for the `str` → `Literal[...]`
  severity assignment — same pattern already used in
  `infrastructure/sqlite/discussions.py` and `infrastructure/postgres/discussions.py` for
  `claim_type=str(row[2])`. Runtime safety is enforced by Pydantic's `ValidationError`, which
  the summarizer's existing per-item exception handling already catches.
- No changes to stores, composition, routes, or `NarrativeService` in this batch — those are
  batches 140-142.

### Commits

- `feat: add ReleaseSummarizer and AdvisorySummarizer (spec 026)`
