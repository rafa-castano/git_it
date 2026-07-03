# Batch 89 — Ask tab answer formatting

## Goal

The Ask tab (GitItGPT, spec 012/013) sometimes produced answers with two
formatting defects: sentences running together with no space after the
sentence-ending punctuation (e.g. `...evidence.The next commit...`), and
excessive blank lines between paragraphs. Instruct the LLM to avoid both via
the chat system prompt, and add a deterministic, unit-tested normalizer that
fixes them when the prompt instruction alone isn't followed — on the backend
for the final non-streaming reply, and on the frontend before every markdown
render (covering the streamed Ask tab path).

Locked decision (from the task brief, not reopened): this repository has no
JS unit-test framework, and this batch does not introduce one. The Python
normalizer is the tested source of truth; the JS mirror was verified for
semantic parity via a one-time manual script (not a repeatable test) and is
documented as an accepted trade-off in spec 016.

## Source of truth

- `specs/016-ask-tab-answer-formatting.md` (new)
- `docs/prompt-contracts/gitit-gpt-system-prompt.md` (updated)

## What was added

- `src/git_it/chat/service.py`:
  - `SYSTEM_PROMPT` gained a new `FORMATTING` paragraph instructing the model
    to write short paragraphs/markdown lists, leave exactly one space after
    sentence-ending punctuation (with a concrete banned run-on example), and
    never leave more than one blank line between blocks. The existing
    `SECURITY` paragraph is unchanged.
  - `normalize_answer_text(text)` — new pure function. Inserts a space when a
    lowercase letter is immediately followed by `.`/`?`/`!` and then an
    uppercase letter, and collapses 3+ consecutive newlines to one blank
    line. Skips fenced code blocks (`` ```...``` ``) entirely via a
    capturing-group split so code content is never rewritten.
  - `ChatService.chat()` now normalizes the final LLM reply text before
    returning it as `ChatResult.reply`.
  - `ChatService.chat_stream()` normalizes `loop.last_text` (used only for the
    turn-cap fallback note) but deliberately does NOT normalize individual
    streamed deltas — rewriting a partial chunk could corrupt a sentence
    boundary that only becomes clear once the next delta arrives. This
    asymmetry is documented in a code comment.
- `src/git_it/static/app.js`:
  - `normalizeAnswerText(text)` — new pure function, a byte-for-byte port of
    the same two regex rules (`([a-z])([.?!])([A-Z])` -> insert a space;
    `\n{3,}` -> `\n\n`; both skip fenced-code segments).
  - `renderMarkdown()` now calls `normalizeAnswerText()` on its input before
    the `marked.parse()` / `DOMPurify.sanitize()` step, so every markdown
    render (Ask tab streaming answers, case-study narratives, and any other
    caller of `renderMarkdown()`) benefits from the fix.
- `docs/prompt-contracts/gitit-gpt-system-prompt.md` — new "Formatting rules
  (spec 016)" section documenting the prompt instruction and the two-sided
  normalizer, plus an evidence-requirement pointer to the new test file.
- `specs/016-ask-tab-answer-formatting.md` — new spec, Status: Accepted.

## Tests added

- `tests/unit/test_answer_text_normalizer.py` (new, 13 tests):
  - Inserts a space after a run-on `.`/`?`/`!` join (three tests, one per
    punctuation mark).
  - Collapses 3+ consecutive newlines to one blank line (two tests).
  - Leaves already-correctly-formatted text untouched.
  - Guard cases: decimal version numbers (`3.12`), a real-world URL
    (`https://github.com/octocat/Hello-World`), an ellipsis, a common
    abbreviation (`e.g.`), and a fenced code block (verifying code content is
    untouched while text outside the fence in the same string is still
    fixed).
  - Empty-string and falsy input do not raise.
- `tests/unit/test_chat_service.py` (+3 tests):
  - `SYSTEM_PROMPT` contains the new formatting instruction (space, blank
    line, short paragraphs/markdown lists).
  - `ChatService.chat()`'s final reply has a run-on sentence join fixed,
    end-to-end through the real service.
  - `ChatService.chat()`'s final reply has excess blank lines collapsed,
    end-to-end through the real service.

Total: 732 passed / 12 skipped → **748 passed / 12 skipped** (16 new tests,
suite stays green).

## Quality gates

- `uv run ruff check .` — all checks passed.
- `uv run ruff format --check .` — all files already formatted.
- `uv run mypy src/` — Success: no issues found.
- `uv run pytest -q` — 748 passed, 12 skipped.

## JS test infrastructure investigation

This repository has no `package.json`, no `node_modules`, and no Jest,
Vitest, Mocha, or Playwright project configuration — only pytest is wired up
(confirmed via `Glob`/`Grep` across the repo root and `tests/`). Per CODEX.md
and the tdd skill's instruction not to invent a test framework that isn't
already wired up, `normalizeAnswerText()` in `app.js` is not covered by an
automated JS test in this batch.

Instead: the JS function is a direct, line-for-line port of the Python
`normalize_answer_text()` regex rules. Semantic parity was verified once
during implementation by running the same case list (run-on joins,
blank-line collapse, and all guard cases) through a throwaway Node.js script
kept outside the repository (in the working scratchpad, never committed) and
confirming identical output to what the Python test suite asserts. This is a
manual, one-time check, not a repeatable automated test — documented in spec
016's Open Questions as an accepted trade-off pending a future JS test
runner decision, which is out of scope for this formatting fix.

## Evaluation harness fit

`evals/` (batch 61) scores per-commit `category`/`risk_level` classification
against hand-labeled golden commits via a live LLM call. It has no fit for a
deterministic, no-LLM-call text-formatting guard — same rationale spec 015
already documented for narrative-opening quality. No eval entry was added.

## Gotchas

- `normalize_answer_text()` (Python) and `normalizeAnswerText()` (JS)
  implement the *same* two regex rules in two languages and must stay in
  sync — each carries a code comment pointing at the other, the same pattern
  batch 88 established for `_extract_overview_opening()` / `loadOverview()`.
- The lowercase-before/uppercase-after guard is deliberately narrow: it
  spares decimals, ellipses, and most abbreviations/URLs by construction (the
  character immediately before the punctuation must be a bare lowercase
  letter), but it is not a full sentence-boundary detector — an unusual
  pattern like a filename ending in a lowercase letter directly followed by
  `.` and an uppercase letter (e.g. `readme.Md`) would still be rewritten.
  Documented as an accepted limitation in spec 016, not a defect.
- `chat_stream()` normalizes `loop.last_text` (the cap-note fallback) but
  intentionally never touches the deltas it already yielded — the frontend's
  per-render normalization of the full accumulated text is what actually
  fixes the streaming path; the two mechanisms are complementary, not
  redundant.

## Commits

- `fix: normalize run-on sentences and excess blank lines in Ask tab answers`
  — (this commit; see `git log -1 --format=%H` for the exact SHA).
