# ADR 013: Sanitize All Client-Side Markdown Rendering with DOMPurify

Status: Accepted
Date: 2026-07-01
Decision makers: TBD

## Context

`marked.parse()` is already used at nine call sites in `src/git_it/static/app.js`
to render LLM-generated Markdown directly into the DOM via `innerHTML` — the
Overview intro, every Case Study section (including the collapsible sub-card and
timeline renderers), with no sanitization step. `marked`'s output is raw HTML;
any HTML embedded in the source Markdown (including literal `<script>` or
`onerror=` attributes) passes through unchanged.

Per ADR 008, all of this text originates from an LLM analyzing **untrusted
repository content** (commit messages, file paths, PR/issue text). If the model
ever echoes attacker-controlled text verbatim inside a Markdown response, the
existing renderers would pass it straight to `innerHTML` — a stored/reflected XSS
vector that predates this ADR.

Spec 012 (GitItGPT) is adding a tenth Markdown-rendering call site: chat replies.
Chat is the first surface where a user interactively, directly drives the model
with an open-ended question, which raises the practical likelihood of eliciting
an echo of injected content compared to the narrative generator's fixed prompt.
This is the trigger to close the gap everywhere at once rather than extend it to
a third surface.

## Decision

Add **DOMPurify** (CDN script, matching the existing `marked`/`chart.js` loading
pattern in `index.html`) and introduce one shared helper,
`renderMarkdown(text, fallbackTag)`, in `app.js`:

- Parses via `marked.parse()`, then sanitizes the resulting HTML via
  `DOMPurify.sanitize()` before it is ever assigned to `innerHTML`.
- **Fails safe, not open**: if either `marked` or `DOMPurify` fails to load (CDN
  blocked, offline), the helper degrades to plain HTML-escaped text
  (`esc(text)` wrapped in a fallback tag), never to unsanitized raw HTML.
- Replaces all nine existing `marked.parse(...)` call sites (Overview intro,
  Case Study sections, sub-cards, timeline, architectural-transition cards) and
  is the one Chat (spec 012 AC-6) uses.

## Consequences

### Positive

- One sanitization boundary for every LLM-rendered Markdown surface in the app;
  closes a latent XSS gap that existed since `marked.parse()` was first
  introduced, consistent with ADR 008's untrusted-content stance.
- Chat, Overview, and Case Study now share one rendering code path — a future
  fix or hardening lands once, not three times.

### Negative

- A new runtime dependency (DOMPurify), loaded via CDN like `marked` and
  `chart.js` already are; a compromised CDN response is a supply-chain risk
  common to all three, not new to this decision.
- No automated CI-run behavioral test exists for the sanitizer (this codebase
  has no JS unit-test runner — see the Quality impact section); coverage relies
  on a static assertion plus a manual browser verification.

### Neutral

- No data model or backend change; this is a rendering-layer change only.
- `marked`'s default table/heading/code output is compatible with DOMPurify's
  default allow-list; no custom tag configuration was needed.

## Alternatives considered

- **Leave `marked.parse()` unsanitized (status quo)**: rejected — chat is
  interactive and adversarially probeable in a way the fixed narrative-generation
  prompt is not; extending the same gap to a third surface without addressing it
  was not acceptable.
- **Sanitize only the new chat surface, leave Overview/Case Study as-is**:
  rejected — both already render the same class of untrusted-influenced LLM
  output; an inconsistent posture would leave two of three surfaces exposed for
  no reason once we are deliberately reviewing this.
- **Drop Markdown entirely, render plain escaped text everywhere**: rejected —
  regresses the already-shipped Case Study UX (headings, lists, tables) for no
  benefit over sanitized rendering.

## Security impact

- DOMPurify strips `<script>`, inline event handler attributes (`onerror=`,
  `onclick=`, …), `javascript:` URLs, etc. from `marked`'s output before it
  reaches `innerHTML`, on every Markdown-rendering surface.
- Complements, does not replace, ADR 008's stance and spec 012 AC-4's
  system-prompt injection hardening: defense in depth at the prompt level (don't
  follow embedded instructions) and at the rendering level (don't execute
  embedded markup) independently.
- Fail-safe fallback: a CDN/script-load failure degrades to escaped plain text,
  never to unsanitized HTML.

## Quality impact

- Static regression test (`tests/unit/test_api_static.py`, this codebase's
  established pattern for frontend assertions — there is no JS unit-test
  runner): asserts the DOMPurify CDN script is present, `DOMPurify.sanitize(` is
  wired into the shared helper, and the old unsanitized
  `typeof marked !== 'undefined' ? marked.parse` pattern no longer appears
  anywhere in `app.js` (proving the retrofit, not just an addition).
- Manual verification (Playwright, per this project's UI-testing mandate): a
  live chat reply containing a Markdown table rendered as an actual HTML table;
  an injected `<img onerror=...>` payload rendered inert (stripped), confirmed
  in-browser.

## Documentation impact

- `docs/specs/012-gitit-gpt-chat.md` AC-6 (Markdown rendering replaces HTML-escaped
  plain text for chat replies).
- `docs/getting-started.md` Ask subsection.

## Links

- ADR 008 (treat repository content as untrusted)
- docs/specs/012-gitit-gpt-chat.md AC-6
