# Spec 016: Ask Tab Answer Formatting

Status: Accepted
Owner: AI Development Flow Agent
Primary agent: AI Development Flow Agent
Supporting agents: Software Engineering Agent, Quality Agent
Created: 2026-07-03
Updated: 2026-07-03

## 1. Summary

The Ask tab (GitItGPT, spec 012/013) sometimes renders answers with two
formatting defects: sentences that run together with no space after the
sentence-ending punctuation (e.g. `...evidence.The next commit...`), and
excessive blank lines between paragraphs. This spec adds an explicit
formatting instruction to the chat system prompt, and a deterministic,
unit-tested text normalizer applied on both the backend (final non-streaming
reply) and the frontend (before every markdown render) as a safety net for
whatever slips past the prompt instruction.

## 2. Problem

`ChatService` (spec 012) builds a system prompt with no explicit formatting
requirements beyond answering the question. In practice the LLM sometimes
omits the space after a period/question mark/exclamation mark when starting a
new sentence, and sometimes emits three or more consecutive newlines. The
frontend renders the answer via `renderMarkdown()` (`marked.parse()` +
`DOMPurify.sanitize()`, ADR 013) with no correction step, so both defects reach
the user as-is: run-on sentences read as broken English, and excess blank
lines create large vertical gaps in the Ask tab transcript.

This also has a second-order effect: `loadOverview()`
(`src/git_it/static/app.js`, spec 015) splits a narrative's opening paragraph
into sentences using `split(/(?<=[.!?])\s+/)`, which depends on a space
following the punctuation to find a sentence boundary at all. A missing space
means that split does not fire, and the "cap to two sentences" logic silently
grabs more text than intended. Fixing the space defect at the render layer
also protects that unrelated slicing logic.

## 3. Goals

- Instruct the LLM (via `SYSTEM_PROMPT` in `src/git_it/chat/service.py`) to
  write short paragraphs or markdown lists, use exactly one space after
  sentence-ending punctuation, and avoid more than one blank line between
  blocks — with a concrete banned run-on example, mirroring how spec 015
  bans its known generic-opening example.
- Add a deterministic, unit-tested `normalize_answer_text()` function that
  fixes both defects when the prompt instruction alone isn't followed.
- Apply the normalizer to the backend's non-streaming `chat()` final reply
  text.
- Add an equivalent, unit-verified-by-parity `normalizeAnswerText()` in the
  frontend, run inside `renderMarkdown()` before `marked.parse()`, since that
  is the one path (ADR 013) that renders all LLM-generated Markdown — the Ask
  tab's streamed answer, case-study narratives, and any other markdown content
  routed through it.
- Keep the guard conservative: it must never rewrite decimals (`3.12`),
  ellipses (`...`), common abbreviations, most URLs, or anything inside a
  fenced code block.

## 4. Non-goals

- Guaranteeing zero false negatives/positives on every possible run-on or
  abbreviation pattern in English prose. This is a best-effort deterministic
  guard, not a full sentence-boundary detector (same posture as spec 015's
  banned-phrase list).
- Normalizing individual `chat_stream()` text deltas server-side. Rewriting a
  partial chunk could corrupt a sentence boundary that only becomes clear once
  the next delta arrives (see Domain concepts). The frontend normalizer, which
  re-renders the full accumulated text on every chunk, is the correct place to
  fix the streaming path.
- Changing the six-section narrative structure, the chat tool-calling loop, or
  any other part of spec 012/013's contract.
- Adding a JS unit-test framework to this repository (see Tests required —
  none exists today; this batch does not introduce one).
- Fetching/rewriting historical (already-persisted) narratives or chat
  transcripts. This only affects newly generated/rendered text going forward.

## 5. Users

- Learner: reads Ask tab answers (and any other markdown rendered via
  `renderMarkdown()`) that read as properly punctuated prose with normal
  paragraph spacing.

## 6. User stories

```md
As a learner asking GitItGPT a question,
I want the answer's sentences to be properly spaced and its paragraphs not to
have huge vertical gaps between them,
so that the answer reads naturally instead of looking broken.
```

## 7. Acceptance criteria

### AC-01 — System prompt requires sentence spacing and bounded blank lines

```gherkin
Given ChatService.SYSTEM_PROMPT
When the prompt text is inspected
Then it instructs the model to write short paragraphs or markdown lists,
  to leave exactly one space after a period/question mark/exclamation mark,
  and to leave no more than one blank line between paragraphs, list items, or
  headings
And it does not remove or weaken the existing SECURITY paragraph.
```

### AC-02 — `normalize_answer_text()` fixes a run-on sentence join

```gherkin
Given a text ending one sentence with "evidence.The next commit..."
When normalize_answer_text(text) is called
Then the result contains "evidence. The next commit..." (one space inserted).
```

### AC-03 — `normalize_answer_text()` collapses excess blank lines

```gherkin
Given a text with three or more consecutive newlines between two paragraphs
When normalize_answer_text(text) is called
Then the result has exactly one blank line (two newlines) between them.
```

### AC-04 — Guard cases are never rewritten

```gherkin
Given a text containing a decimal version number (e.g. "Python 3.12"), an
  ellipsis ("..."), a common abbreviation ("e.g."), a URL
  ("https://github.com/octocat/Hello-World"), or a fenced code block
When normalize_answer_text(text) is called
Then none of those substrings are altered.
```

### AC-05 — Backend applies the normalizer to the final non-streaming reply

```gherkin
Given ChatService.chat() receives a final (non-tool-calling) LLM turn whose
  text has a run-on sentence join or excess blank lines
When chat() returns
Then ChatResult.reply is the normalized text.
```

### AC-06 — Frontend normalizer runs before every markdown render

```gherkin
Given renderMarkdown(text) is called with text containing a run-on sentence
  join or excess blank lines
When renderMarkdown builds its output
Then normalizeAnswerText(text) runs first, and the guard cases (decimals,
  URLs, ellipses, code fences) are left untouched, matching the same
  semantics as the Python normalize_answer_text() (verified by parity, not by
  a shared runtime — see Tests required).
```

## 8. Domain concepts

- **Run-on sentence join**: a sentence-ending punctuation mark (`.`, `?`, `!`)
  immediately followed by an uppercase letter, with a lowercase letter
  immediately before the punctuation mark — the narrow, conservative pattern
  this spec detects and fixes by inserting one space.
- **Excess blank lines**: three or more consecutive newline characters,
  collapsed to exactly two (one blank line).
- **Fenced code block**: a Markdown code fence delimited by matching triple
  backticks. Content inside is passed through both normalization rules
  unchanged, since code often legitimately contains dot-then-uppercase
  sequences (e.g. `x = 3.12\ndef Foo():`) that must not be rewritten.
- **Partial-chunk corruption risk**: why the streaming path is not normalized
  server-side per-delta — a delta boundary could fall exactly between the
  period and the next letter, or between two `` ` `` characters of a code
  fence, and rewriting a delta in isolation could not correctly detect the
  fence or the following letter's case.

## 9. Inputs and outputs

Inputs:

- The full final reply text (Python, non-streaming `chat()` path) or the full
  accumulated rendered text (JS, at every markdown render call).

Outputs:

- `normalize_answer_text(text: str) -> str` (Python, pure function, no side
  effects) in `src/git_it/chat/service.py`.
- `normalizeAnswerText(text)` (JS, pure function) in
  `src/git_it/static/app.js`, called inside `renderMarkdown()`.

No new persisted fields or API response fields are introduced.

## 10. Evidence requirements

Not applicable in the CODEX.md "evidence before interpretation" sense — this
spec is a deterministic text-formatting fix, not an evidence-grounded claim
about repository history. The relevant discipline here is: the fix must not
alter any text it isn't explicitly designed to fix (the guard cases in AC-04).

## 11. Failure modes

| Failure | Behavior |
|---|---|
| LLM still produces a run-on join or excess blank lines despite the prompt instruction | Caught by `normalize_answer_text()` / `normalizeAnswerText()` before display. |
| A genuinely ambiguous `.X` pattern that isn't a decimal/URL/abbreviation but also isn't a real sentence boundary | Not perfectly distinguishable by this heuristic; accepted as a known limitation, same posture as spec 015's banned-phrase list. |
| Frontend and backend normalizers drift out of sync after a future edit | Not automatically detected (no shared runtime). Mitigated by a code comment on both sides and a JS/Python parity check performed manually at review time (see Tests required). |
| `normalize_answer_text("")` / `normalizeAnswerText('')` | Returns `""`, does not raise. |

## 12. Security considerations

None beyond the existing posture. The normalizer only rewrites already-trusted
LLM output text (whitespace/punctuation insertion), not raw repository data,
and does not change what markdown/HTML is allowed through
`DOMPurify.sanitize()` — it runs strictly before `marked.parse()`, on the
Markdown source text.

## 13. Privacy considerations

None. No new data is collected, logged, or transmitted.

## 14. Observability

None added. This is a silent, deterministic text transform — there is no
generic-boilerplate-style detection signal to log here (unlike spec 015),
because there is no "quality" judgment being made, only a mechanical
formatting fix.

## 15. Tests required

### Unit tests (Python — TDD, written first)

`tests/unit/test_answer_text_normalizer.py`:

- Inserts a space after a run-on `.`/`?`/`!` join.
- Collapses 3+ consecutive newlines to one blank line.
- Does not touch already-correctly-formatted text.
- Guard cases: does not split a decimal version number, does not rewrite
  inside a URL, does not touch an ellipsis, does not split a common
  abbreviation, does not rewrite text inside a fenced code block (while still
  fixing text outside the fence in the same string).
- Empty-string input returns empty string without raising.

`tests/unit/test_chat_service.py` (added in this batch):

- `SYSTEM_PROMPT` contains the new formatting instruction (space, blank line,
  short paragraphs/markdown lists).
- `ChatService.chat()`'s final reply is normalized (run-on join fixed, excess
  blank lines collapsed) — end-to-end through the real service, not just the
  pure function.

### Frontend (JS)

**Investigated**: this repository has no JS unit-test framework wired up — no
`package.json`, no `node_modules`, no Jest/Vitest/Mocha config, no existing
`*.test.js` files. Per CODEX.md and the tdd skill ("do not invent a test
framework that isn't wired up"), this batch does not introduce one.

`normalizeAnswerText()` is implemented as a byte-for-byte port of the same two
regex rules used by `normalize_answer_text()` (`([a-z])([.?!])([A-Z])` ->
insert a space; `\n{3,}` -> `\n\n`; both skip fenced-code segments split via
`` /(```[\s\S]*?```)/ ``). Semantic parity between the two was verified during
implementation by running the exact same case list (run-on joins, blank-line
collapse, decimal/URL/ellipsis/abbreviation/code-fence guards) through a
throwaway Node.js script outside the repository and confirming identical
output to the Python test suite — this is a one-time manual verification, not
a repeatable automated test, and is documented here as the accepted trade-off
until this project adopts a JS test runner. AC-04/AC-06's guard-case
requirement is therefore fully covered by the Python suite (the shared logic
under test), with the JS side additionally code-reviewed for drift.

### Evaluation required

Not added. `evals/run.py` is structured around scoring per-commit
`category`/`risk_level` classification against hand-labeled golden commits and
requires a live LLM call — it does not fit a deterministic text-formatting
guard with no LLM call of its own. Same rationale as spec 015's "Evaluation
required" section. The unit tests above are the correct and sufficient
coverage for this deterministic transform.

## 16. Documentation impact

- `docs/prompt-contracts/gitit-gpt-system-prompt.md` updated with a
  "Formatting rules (spec 016)" section documenting the new prompt
  instruction and the two-sided (backend + frontend) normalizer.
- `docs/progress/analysis/batch-89-ask-tab-answer-formatting.md` records this
  batch's work per the repository's commit/documentation discipline.

## 17. ADR impact

None. This is a prompt refinement plus an additive deterministic text
transform within the existing chat (spec 012/013) and rendering (ADR 013)
architecture; no architectural boundary changes.

## 18. Open questions

- **Should the JS and Python normalizers be unified into one implementation
  (e.g. via a shared build step or a tiny WASM/transpiled module)?**
  Assumption made: no, keep them as two small, independently readable
  implementations with an explicit "keep in sync" comment on both sides, same
  as spec 015's precedent for `_extract_overview_opening()` /
  `loadOverview()`. Revisit only if this project adopts a JS build pipeline
  for other reasons.
- **Should `chat_stream()` normalize deltas server-side after all, e.g. by
  buffering a small lookahead window?** Assumption made: no — added
  complexity and latency for a problem the frontend already solves correctly
  by re-rendering the full accumulated text on every chunk. Documented as a
  non-goal.
- **Should a JS test runner (Vitest/Jest) be introduced in this batch to
  properly unit-test `normalizeAnswerText()`?** Assumption made: no — that is
  a standalone infrastructure decision (tooling, CI wiring, `package.json`)
  out of scope for a formatting bug fix, and CODEX.md's "small, reversible
  changes" principle argues against bundling it here. Flagged as a candidate
  follow-up if more frontend logic accumulates that needs isolated testing.

## 19. Out of scope

- A JS unit-test framework/build pipeline.
- Server-side per-delta stream normalization.
- Rewriting previously persisted narratives or chat transcripts.
- Any change to the six-section case-study structure or the chat tool-calling
  loop.
