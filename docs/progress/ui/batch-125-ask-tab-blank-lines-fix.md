## Batch 125 — Fix blank-line-per-sentence rendering in Ask tab answers

### Goal

The user reported the Ask tab's assistant answers rendered with a visible blank
line between every sentence/line, even for short two- or three-sentence
answers. Root cause: `.ask-msg` (`src/git_it/static/app.css`) sets
`white-space: pre-wrap` so the plain-text user bubble preserves the user's own
typed line breaks. That rule was also inherited by the assistant bubble's
`.markdown-body`, which holds real `marked.js`-rendered HTML, not plain text.

CommonMark's "soft break" — a single source newline inside a paragraph — is
left as a literal `\n` character inside the rendered `<p>` tag by design,
meant to collapse into ordinary whitespace the way browsers normally render
HTML. With `pre-wrap` inherited onto that HTML, every one of those soft
breaks instead rendered as a real visible line break, stacked visually next to
the `<p>` tag's own `margin-bottom`, producing the reported "blank line
between every line" defect — for any answer where the model happened to put
sentences on separate source lines within one logical paragraph, which is a
common LLM output style not prohibited by SYSTEM_PROMPT's existing
"no more than one blank line" formatting rule (that rule only bounds
*multiple* blank lines, not a single line break between sentences).

### What changed

**`src/git_it/static/app.css`** — `.ask-msg-assistant .markdown-body` gained
`white-space: normal;`, overriding the inherited `pre-wrap` from `.ask-msg`.
The user bubble (`.ask-msg-user`, plain escaped text with no markup of its
own) is unaffected — it still needs `pre-wrap` to preserve a user's own typed
line breaks correctly.

### Verification (live, via Playwright — not just described)

No JS/CSS unit-test framework exists in this repo (confirmed absence again,
same posture as batches 89/90/92/93/96/113) — this was live browser
verification, not an automated regression test.

- Started the real server from the repo root, opened the dashboard, navigated
  into the `odysseus` repository's Ask tab.
- Injected a synthetic assistant message via `_appendAskMessage('assistant',
  text)` (the same function the real streaming/non-streaming chat path calls)
  using a reproduction string with single newlines between sentences, mirroring
  the user's own reported example ("I don't have enough context to answer
  your question." / "\"The first decision\" could refer to many things." /
  "It might mean the first architectural decision in the repository...").
- **Before** (temporarily re-applied `white-space: pre-wrap` inline to
  reproduce the pre-fix state): screenshot showed each sentence on its own
  line with a visible gap — reproducing the exact reported defect.
- **After** (the actual shipped fix): screenshot showed one continuous,
  naturally-wrapping paragraph with no gaps between sentences.
- Confirmed `getComputedStyle(mdBody).whiteSpace === 'normal'` on the
  assistant bubble, and that `marked.parse()` does in fact leave the raw `\n`
  characters inside the single `<p>` tag it produces (`pCount: 1`),
  confirming the CommonMark soft-break hypothesis empirically rather than
  assuming it.

### Gotchas

- This is a CSS-only, single-selector fix. No Python, JS logic, or prompt
  changes were needed — `normalize_answer_text()`/`normalizeAnswerText()`
  (spec 016) correctly leave single soft-break newlines alone by design (only
  collapsing 3+ consecutive newlines); this defect lived entirely in
  presentation, not in the text the model/normalizer produced.
- The bug reproduces regardless of which LLM answers the question — it is a
  property of how `marked.js` renders any multi-sentence paragraph combined
  with the inherited `pre-wrap`, not a model-specific formatting quirk.
- Ruling out an unrelated concern first: confirmed via a separate live check
  that day that `GET /api/repos` correctly reads `.data/git-it/ingestion/
  git-it.sqlite3` relative to the server process's actual working directory
  (`Path.cwd()` fallback in `get_project_root()`, `src/git_it/api/deps.py`) —
  an earlier "no repositories analyzed" report in this session turned out to
  be an unrelated invocation issue (server started from `docs/`, not the repo
  root), not a code defect, and needed no fix.

### Commits

- `fix: stop pre-wrap from turning markdown soft-breaks into blank lines in Ask tab`
