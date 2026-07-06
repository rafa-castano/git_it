## Batch 126 — Linkify commit SHAs and file/folder paths in Ask tab answers

### Goal

Extend the existing commit-SHA and file/folder-path linkification (`_linkifyCommitShas`,
spec 020's `_linkifyPaths`) — already live in the Case Study narrative — to GitItGPT's
Ask tab, so a commit or backtick-wrapped path the model cites in an answer becomes a
clickable link to the real commit/blob/tree on GitHub, in both the non-streaming and
streaming render paths.

This is a reuse/wiring batch, not a new spec: the linkification mechanism, its regex
allow-lists, and its documented security posture were already fully specified and
shipped by spec 020 ("Fix 6" for SHAs, the full spec for paths). Nothing new is being
invented — an already-audited capability is being pointed at one more render call site.

### What changed

**`src/git_it/static/app.js`**

- New `_linkifyAskAnswerHtml(html)` — sources `canonical_url`/`default_branch` from the
  existing `currentRepoMeta` global (already populated whenever a repo is opened; the
  Ask tab only renders while a repo is open, so no new fetch is needed) and chains
  `_linkifyPaths(_linkifyCommitShas(html, canonicalUrl), canonicalUrl, defaultBranch)` —
  the exact ordering `_linkifyPaths`' own doc comment requires.
- `_appendAskMessage`: the assistant branch now wraps `renderMarkdown(text)` in
  `_linkifyAskAnswerHtml(...)` before insertion.
- The SSE streaming delta handler: `bubbleEl.querySelector('.markdown-body').innerHTML`
  now goes through `_linkifyAskAnswerHtml(renderMarkdown(accumulated))` on every
  incoming chunk, so links appear progressively as the answer streams in, not only
  once it's complete.

### Security considerations (verified live, not just reasoned about)

The user explicitly asked to keep XSS and prompt-injection risks in mind, since this
touches links built from model output. Both were checked empirically, not just
assumed, via a live Playwright session:

- **No new security primitive.** `_linkifyCommitShas`/`_linkifyPaths` are unmodified —
  same hex-only SHA regex, same `_PATH_SAFE_CHARSET` allow-list (`[A-Za-z0-9._/-]`
  only), same `..`/leading-`/`/`://` rejections, same `encodeURIComponent` on path
  segments, same `target="_blank" rel="noopener"`. This batch only adds one more call
  site for that existing, already-reviewed logic.
- **Both linkifiers run on HTML that has already passed through `marked.parse()` +
  `DOMPurify.sanitize()`** (inside `renderMarkdown`), so any literal `<`/`>`/quote
  characters in the model's raw text are already entity-escaped before the linkify
  regexes ever see them. Verified live: a crafted answer containing
  `` `"><script>alert(1)</script>` `` rendered as an inert, HTML-escaped `<code>` span
  (`&quot;&gt;&lt;script&gt;...`) — no live `<script>` tag in the DOM, and the escaped
  text (containing `&`/`;`, outside the safe charset) was correctly left un-linkified.
- **Path traversal rejected.** A crafted `` `../../etc/passwd` `` span was left as
  plain, un-linkified `<code>` text — `_isSafePathLikeString`'s `..`-substring check
  fires exactly as it does in the Case Study path.
- **No new prompt-injection surface.** Linkification runs entirely client-side, after
  the model has already produced its final answer text — it cannot influence what the
  model says or does, only how already-generated text is visually decorated. The
  existing SYSTEM_PROMPT's untrusted-tool-output posture (treat tool results as data,
  never instructions) is unaffected and unchanged by this batch.
- **Fabricated/hallucinated SHAs and paths are an accepted, pre-existing risk class**
  (spec 020 Non-goals: "paths are linked optimistically... exactly like SHA-linking
  does not verify the SHA exists"), not a new one introduced here — a wrong link 404s
  on GitHub, it does not redirect off-domain, since `canonical_url` (the link's
  authority/domain) is always the trusted, stored repo metadata, never taken from the
  LLM's own text.

### Verification (live, via Playwright — not just described)

No JS unit-test framework exists in this repo (confirmed absence again, same posture
as batches 89/90/92/93/96/113/125) — this was live browser verification against the
real running server and a real analyzed repository (`odysseus`), not an automated
regression test.

- Injected a synthetic assistant answer citing a real commit SHA
  (`93569b141b92780e6f175282a195ec9727ba42f5`, fetched live from `GET /api/repos/.../commits`)
  and a backtick-wrapped real file path (`` `src/git_it/api/app.py` ``) through the
  actual `_appendAskMessage` function. Both rendered as `<a>` tags with correct
  `href`s (`.../commit/93569b...` and `.../blob/main/src/git_it/api/app.py`),
  `target="_blank"`, `rel="noopener"`.
- Confirmed the two adversarial cases above (XSS attempt, path traversal attempt) both
  render safely with no link and no live script tag.
- Confirmed the streaming path: linkifies mid-stream on a partial chunk (SHA only) and
  again once the full answer (SHA + path) has accumulated, with both links present and
  correct at completion.
- `node --check src/git_it/static/app.js` — exits 0.

### Gotchas

- `_linkifyAskAnswerHtml` must run over the HTML `renderMarkdown()` already produced
  (post-DOMPurify), not over the raw model text — this mirrors the Case Study path's
  established ordering exactly (`_linkifyPaths(_linkifyCommitShas(tabPanels, ...))`
  runs on rendered `tabPanels` HTML, never on `data.narrative` directly) and is what
  keeps the escaping guarantees intact.
- Only the assistant's rendered answer is linkified — the user's own message bubble
  (plain `esc(text)`, no markup) and the "thinking…" placeholder are untouched, same
  scoping as the existing Case Study linkification (narrative only, not UI chrome).

### Commits

- `feat: linkify commit SHAs and file paths in Ask tab answers`
