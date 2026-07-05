## Batch 113 — Fix two defects found in the first live Playwright QA sweep

### Goal

This session ran the first-ever live Playwright QA sweep of the entire 16-item UX/
feature program (batches 84-112), against a real running server, since every prior
batch's "manual/e2e verification steps" section had documented what *should* be
checked but never actually been driven through a browser. The sweep confirmed 11 of
16 items work correctly live, and surfaced two real defects, both fixed here with
regression coverage.

### Defect 1 — sidebar drag-resize silently broken below 900px viewport width

**What was wrong.** `src/git_it/static/app.css` had:
```css
@media (max-width: 900px) {
  aside { width: 160px; }
}
```
This has equal CSS specificity to the base `aside { width: var(--sidebar-width, 210px); ... }`
rule, and — being declared later — wins outright below 900px, discarding the
drag-resize feature's CSS custom property entirely. The resize handle stayed visible
and draggable, and `localStorage`/the `--sidebar-width` var still updated correctly on
every drag, but the sidebar's rendered width never changed: a silent, zero-feedback
no-op for any window narrower than 900px.

**Context worth being explicit about:** batch 93's own progress doc *already
documented this exact cascade behavior* and called it "intentional... and not a bug."
This batch reverses that call — not because the CSS analysis was wrong (it wasn't),
but because live QA showed the resulting UX (drag a handle, watch nothing happen,
with the value silently persisted anyway) is a real defect from a user's perspective,
regardless of which CSS rule "correctly" wins the cascade.

**Fix.** `aside { width: var(--sidebar-width, 160px); max-width: 220px; }` inside the
media query: falls back to the same 160px pre-drag default, respects a user's
dragged/persisted width, but caps it at 220px so a desktop-dragged wide value (up to
480px) doesn't dominate a narrow viewport. Desktop behavior (>900px) is unaffected —
that rule lives entirely inside the media query.

**Verification (live, via Playwright — not just described):**
- At 686px viewport, before the fix: aside width stuck at 160px regardless of a
  persisted 423px `--sidebar-width`.
- After the fix, same viewport, same persisted value: aside renders at 220px (the new
  cap), not 160px.
- Set `--sidebar-width` to 180px (within the 150-220 narrow-viewport range) at 686px:
  aside renders at 180px — confirms the fix responds across the range, not just
  clamping to a fixed number.
- Resized back to 1400px: aside renders at the same 180px with no cap applied —
  confirms desktop behavior is unchanged by this fix.

No JS/CSS unit-test framework exists in this repo (confirmed absence again, same
posture as batches 89/90/92/93) — this was a live Playwright verification, not an
automated regression test. `node --check src/git_it/static/app.js` still exits 0
(unaffected file, but re-checked since the fix is adjacent).

### Defect 2 — false positive in the generic-opening quality guard

**What was wrong.** `_GENERIC_OPENING_PHRASES` in
`src/git_it/repository_ingestion/application/narrative_service.py` included the
standalone entry `"in the weeks that followed"`. Live QA regenerated a case study and
got a genuinely repo-specific, well-written opening ("Odysseus is a self-hosted AI
agent platform that integrates a conversational assistant with real-world
productivity tools ... producing 230 additional commits in the weeks that
followed.") — and `check_opening_quality()` flagged it as generic boilerplate,
purely because that one common, unremarkable temporal phrase happened to appear at
the end of an otherwise specific sentence. Confirmed via the live server log: `WARNING
Generic case study opening detected ... matched boilerplate pattern 'in the weeks
that followed'`.

The phrase is too generic a substring to reliably distinguish boilerplate from
ordinary specific writing. The actual known-bad pattern this guard exists to catch
(the pre-spec-015 narrative style, e.g. "This case study traces what happened in the
weeks that followed, using the commit history as evidence.") is still caught by the
other three phrases already in the list: `"this case study traces"`, `"using the
commit history as evidence"`, and `"traces what happened"` — removing this one entry
does not weaken detection of the real pattern.

**Fix (TDD).** RED: added
`test_check_opening_quality_does_not_flag_specific_opening_using_a_common_temporal_phrase`
to `tests/unit/test_narrative_service.py`, using the exact style of opening found in
QA — confirmed it failed for the right reason (the phrase was still in the list).
GREEN: removed `"in the weeks that followed"` from `_GENERIC_OPENING_PHRASES`. All 36
tests in `test_narrative_service.py` pass, including the pre-existing tests that
assert the real boilerplate pattern is still flagged.

### Tests added

- `tests/unit/test_narrative_service.py`: +1 test (see above).

Full suite: **874 passed, 21 skipped** (was 873 passed / 21 skipped before this
batch).

Quality gates: `ruff check .` (all checks passed), `ruff format --check .` (169 files
already formatted), `mypy src/` (no issues, 70 source files).

### Gotchas

- This is the first batch in the whole 16-item program where the plan's
  "Frontend behavior: ... drive the dashboard with the Playwright MCP" verification
  step was actually performed, rather than left as a documented-but-unexecuted
  checklist. Doing so is what surfaced both defects — neither was visible from
  `node --check` or the Python test suite alone.
- Seeding realistic data (repo stars/languages/default-branch/discussion-evidence) via
  the real domain/store classes — not hand-rolled SQL — made it possible to visually
  verify specs 019/020/022 end-to-end in a local environment without a `GITHUB_TOKEN`.
- Defect 1 is a reminder that a CSS-cascade analysis being *correct* (batch 93's doc
  got the mechanism exactly right) doesn't mean the resulting behavior is *desirable*
  — the same facts support "intentional, documented trade-off" and "silent, confusing
  no-op" as descriptions; only driving it in a real browser resolved which one it was.

### Commits

- `fix: respect dragged sidebar width on narrow viewports and remove a generic-opening false positive`
