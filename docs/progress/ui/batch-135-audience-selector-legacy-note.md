## Batch 135 — Explain why the Beginner/Expert selector has no effect on legacy commits

### Goal

User reported the Commits tab's Beginner/Expert selector "does nothing — the same text is
shown." Investigated before touching anything, since the report could point to a broken
toggle or to a data/UX gap.

### Investigation (evidence before interpretation)

1. Checked the local SQLite DB directly: for the `odysseus` repo, 60 of 200 analyzed commits
   have genuinely distinct `summary_beginner`/`summary_expert` text; the other 140 have both
   fields `null` (analyzed before dual-audience summaries existed) and only a legacy
   `summary` field.
2. Verified live via Playwright, both by calling `_setCommitAudience()` directly and by
   driving the real `<select>` element (`browser_select_option`, exercising the actual
   `onchange="_setCommitAudience(this.value)"` DOM wiring): for a commit with both fields
   populated, toggling Beginner ↔ Expert correctly swapped the displayed text every time — the
   toggle mechanism itself was never broken.
3. Checked a commit with `summary_beginner`/`summary_expert` both `null`: toggling correctly
   left the text unchanged, because `app.js`'s existing fallback
   (`c.summary_beginner !== undefined && c.summary_beginner !== null ? ... : (c.summary ||
   '')`) has nothing to switch between for that commit — this is the real behavior the report
   describes.
4. Checked `_updateAudienceBanner` (the existing repo-level "beginner summaries haven't been
   generated yet" banner): it only fires when **zero** commits in the repo have the selected
   audience's field (`_tlAllCommits.some(...)` is false). For a repo in the *mixed* state above
   (60 with data, 140 without), `hasAny` is `true`, so the banner stays hidden — there was no
   per-commit signal telling the user why one specific commit's text wasn't changing.

**Root cause**: not a broken selector — a silent, unindicated fallback for commits analyzed
before dual-audience summaries existed, in repos with mixed old/new analysis coverage. The
repo-level banner only covers the "nothing at all" case, not the much more common "some
commits do, some don't" case.

### What changed

**`src/git_it/static/app.js`**
- Row-render loop: factored the existing inline condition into a named
  `hasDualAudience` boolean (previously computed inline, now reused).
- When a commit lacks dual-audience data (`hasDualAudience` is `false`), its expanded detail
  now shows a small `(single-summary analysis)` note, using the existing `data-tip` tooltip
  system (not a native `title=`, matching this codebase's established convention since batch
  85) rather than a new UI element.
- New `TIPS.tlLegacySummary` entry: "This commit was analyzed before beginner/expert summaries
  existed, so the Beginner/Expert selector has no effect on it — re-analyze the repository to
  generate audience-specific versions."
- The note is per-commit, not per-repo — it appears only on rows that actually fall back,
  leaving rows with real dual-audience data unchanged (verified no note appears there).

### Verification (live, via Playwright — not just described)

No JS unit-test framework exists in this repo (confirmed absence again, same posture as
batches 89/90/92/93/96/113/125/126/127/128) — live browser verification against the real
running server and the real `odysseus` repository's mixed-coverage data.

- Expanded a legacy (fields-`null`) commit's detail: confirmed `.tl-legacy-note` is present,
  with the exact expected text.
- Expanded a dual-audience commit's detail: confirmed `.tl-legacy-note` is absent.
- Confirmed `TIPS.tlLegacySummary` resolves to the full explanatory tooltip text.
- Re-confirmed (from the prior investigation step, still valid) that toggling Beginner ↔
  Expert on a dual-audience commit still correctly swaps its text — this batch only adds an
  explanatory note for the fallback case, it does not touch the working toggle path.
- `node --check src/git_it/static/app.js` — exits 0.

### Gotchas

- This is **not** a backend/data bug — re-analyzing a repository (the existing `+ Analyze`
  flow) already produces genuine dual-audience summaries for newly-analyzed commits; this
  batch only makes the *existing* accepted gap (pre-dual-audience commits keep one summary
  until re-analyzed) visible instead of silent, matching the "backfill gap accepted, not
  solved, but at least surfaced" posture already used elsewhere in this codebase (e.g. spec
  019/020's stars/languages/default-branch backfill gaps).
- Deliberately did not change `_updateAudienceBanner`'s repo-level "zero coverage" condition —
  it still serves its original purpose (a same, clearer message when a repo has *no*
  dual-audience data at all); the new per-commit note covers the different, more common
  "mixed coverage" case that condition doesn't reach.

### Commits

- `fix: explain why Beginner/Expert selector has no effect on pre-dual-audience commits`
