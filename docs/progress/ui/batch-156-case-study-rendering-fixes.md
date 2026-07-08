## Batch 156 — Case-study rendering fixes (SHA-attribute linkify, path linking, lessons highlight)

### Goal

Fix three defects in the case-study rendering path in `src/git_it/static/app.js`, all
confirmed on production. They share one theme (case-study rendering correctness), so they
land in one batch.

### Why

1. **Bug 2 — corrupted markup above the first timeline node.** `_linkifyCommitShas` ran a
   blind whole-string `.replace()`, so a bare commit SHA appearing inside a tag attribute
   (e.g. a timeline node's `title="…up to commit \`c0dab29\`…"`) got an `<a href>` injected
   *into* the attribute value, terminating the attribute early and spilling broken markup
   (`https:`, `github.com`, …) as stray text above the first stage dot. The old negative
   lookbehind only guarded `href=`, not other attributes.
2. **Bug 3 — every Case Study file link 404'd.** `isLinkablePath` returned
   `hasSlash || hasKnownExtension`, so a bare basename like `ports.py` (extension, no slash)
   was linked to `/blob/<branch>/ports.py` at the repo *root*, which 404s because the real
   file is nested. A bare basename cannot be located in the repo tree.
3. **Bug 4 — Engineering Lessons point 7 wrongly highlighted.** `_renderSectionCards`
   flagged any card whose title matched `/architect|key pattern|design pattern|structural
   pattern/i` as an architectural-pattern card (🏛 icon, highlighted, auto-expanded). The
   Engineering Lessons lesson "Streaming Changes the Architecture, Not Just the UI" matched
   `/architect/i` and was wrongly highlighted.

### What was changed

**`src/git_it/static/app.js`**
- `_linkifyCommitShas` is now **tag-aware**: it splits the HTML with `/<[^>]*>|[^<]+/g`,
  returns any tag segment untouched, and only linkifies hex runs inside text-between-tags
  segments. Tag attributes are never rewritten. The old `(?<!href=…)` lookbehind is removed
  (no longer needed — tags are excluded wholesale).
- `isLinkablePath` now requires a path separator: `return text.includes('/')`. A bare
  basename is no longer linkable. `_LINKABLE_EXTENSIONS`, `_isFolderPath`, and
  `_pathToGithubUrl` are unchanged (still used for folder/file kind detection and URL
  building).
- `_renderSectionCards(content)` → `_renderSectionCards(content, sectionTitle)`, and
  `isArchPattern` is now gated by `sectionTitle !== 'Engineering Lessons'` before the regex
  test. The call site in `loadCaseStudy` passes the section title:
  `_renderSectionCards(s.content, s.title)`. The `.cs-arch-pattern-card` feature and its CSS
  are untouched — the highlight is scoped, not removed.

### Tests added

`tests/unit/test_api_static.py` (3 new source-string assertion tests over the served
`app.js`, matching this file's convention — there is no JS engine; all three were RED first,
GREEN after):
- `test_static_app_js_linkify_commit_shas_is_tag_aware` — asserts the served source contains
  the tag-skipping split `/<[^>]*>|[^<]+/g` and that the old blind `(?<!href=` lookbehind is
  gone.
- `test_static_app_js_linkable_path_requires_a_slash` — asserts `isLinkablePath` no longer
  contains `hasSlash || hasKnownExtension` and now gates on `text.includes('/')`.
- `test_static_app_js_arch_pattern_highlight_excludes_engineering_lessons` — asserts
  `loadCaseStudy` calls `_renderSectionCards(s.content, s.title)` and that the isArchPattern
  computation is gated by `sectionTitle !== 'Engineering Lessons'`.

The existing `test_static_app_css_small_text_uses_text_not_accent[.cs-arch-pattern-card ...]`
CSS test stays green — the highlight feature and its CSS rule are preserved.

Full suite: **1176 passed, 33 skipped** (+3 new tests, no regressions).

### Gotchas

- Frontend tests in this repo assert on the served `app.js` source string (no JS runtime),
  so these are structural assertions on the code, not behavioral browser tests. That is the
  established convention in `test_api_static.py`.
- Bug 4's fix deliberately preserves the `.cs-arch-pattern-card` feature and CSS; only the
  *trigger* is scoped. Removing the feature would have broken the existing CSS-rule test.

### Commits

- `fix: correct case-study SHA-attribute linkify, path linking, and lessons highlight`
