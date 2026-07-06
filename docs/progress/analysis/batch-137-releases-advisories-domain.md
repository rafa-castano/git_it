## Batch 137 — Releases and Security Advisories domain model (spec 026, slice 1)

### Goal

Lay the domain foundation for spec 026 (GitHub Releases and Security Advisories
as cited narrative evidence): the four domain shapes only — `Release`,
`ReleaseEvidence`, `SecurityAdvisory`, `AdvisoryEvidence`. This is the first of
the spec-026 build slices; the fetchers, the LLM summarizers, the persistence
stores, the ingest wiring, and the narrative integration land in later batches,
matching the TDD order the spec mandates (domain → fetchers → summarizers →
stores → wiring → narrative).

### Why

Spec 026 is spec-only; nothing was implemented when it was authored (batch
129). Building it bottom-up keeps each slice independently green and
reviewable, mirroring exactly how spec 022 (Discussions) and spec 025
(README/CHANGELOG) were built. The domain models have no external dependencies
(no GitHub API, no LLM), so they are the safest place to start and everything
else builds on them.

### What was added

**`domain/releases.py`** (new)
- `Release` — frozen dataclass, the raw fetched candidate. **Never persisted or
  serialized**: no code path writes its `body` (raw release-notes markdown)
  anywhere. Mirrors `Discussion`'s "raw text never rendered" guarantee (spec
  022, Security considerations).
- `ReleaseEvidence` — Pydantic `BaseModel`, the schema-validated, persisted,
  narrative-facing LLM output (mirrors `DiscussionEvidence`). A
  `field_validator` enforces `release_url` against
  `^https://github\.com/[^/]+/[^/]+/releases/tag/\S+$` — the deterministic,
  unit-testable form of CODEX.md's evidence-link requirement. `confidence` is
  bounded `[0.0, 1.0]`; `claim_type` is
  `Literal["breaking_change", "feature_release", "bugfix_release",
  "security_release"]`.

**`domain/advisories.py`** (new)
- `SecurityAdvisory` — frozen dataclass, the raw fetched candidate. **Never
  persisted or serialized**: no code path writes its `description` (raw,
  community/maintainer-authored text) anywhere.
- `AdvisoryEvidence` — Pydantic `BaseModel`, the schema-validated, persisted,
  narrative-facing LLM output. A `field_validator` enforces `advisory_url`
  against `^https://github\.com/[^/]+/[^/]+/security/advisories/GHSA-[0-9a-z-]+$`.
  `confidence` is bounded `[0.0, 1.0]`; `severity` is
  `Literal["low", "medium", "high", "critical"]` (GitHub's own four documented
  severity values), rejected at construction if out of range — closing a path
  where a prompt-injected advisory description could otherwise inflate/deflate
  the reported severity.

### Tests added

- `tests/unit/test_releases_domain.py` (10 tests): valid construction; rejects
  missing/empty/non-GitHub/wrong-path `release_url`; rejects out-of-range
  `confidence`; rejects invalid `claim_type`; defaults `limitations`; `Release`
  holds raw fields with no validation.
- `tests/unit/test_advisories_domain.py` (10 tests): valid construction;
  rejects missing/empty/non-GitHub/wrong-path `advisory_url`; rejects
  out-of-range `confidence`; rejects invalid `severity`; defaults
  `limitations`; `SecurityAdvisory` holds raw fields with no validation.

Full suite: **1012 passed, 27 skipped** (was 992 passed / 27 skipped before
this batch; +20 passing domain tests).

### Gotchas

- The `release_url` regex uses `\S+` (not `[^/]+`) for the tag segment because
  tags legitimately contain dots (`v1.2.3`) and GitHub percent-encodes any `/`
  a tag name might contain — `\S+` is correct and not over-restrictive, while
  still excluding whitespace.
- Nothing here fetches or summarizes anything yet: `Release`/`SecurityAdvisory`
  have no producer and `ReleaseEvidence`/`AdvisoryEvidence` have no writer other
  than direct construction in tests. Both are dead code until the
  fetcher/summarizer/store/wiring batches land — intentional, so each slice
  stays small and green.

### Commits

- `feat: add Release/SecurityAdvisory domain models and evidence types (spec 026)`
