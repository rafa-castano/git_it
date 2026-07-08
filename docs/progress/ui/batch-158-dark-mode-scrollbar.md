## Batch 158 — Theme-aware scrollbars (dark mode)

### Goal

In dark mode the scrollbars kept the browser's UA-default look (light-gray track/thumb),
so they clashed with the dark theme — most visible in the **Ask** tab once a conversation
has several exchanges and the transcript scrolls. Make the scrollbar adopt the active
theme's colors in both light and dark.

### What was added

- `static/app.css`: a small themed-scrollbar block right after `:focus-visible`. It drives
  **both** cross-browser mechanisms off the existing theme variables:
  - `scrollbar-width: thin` + `scrollbar-color: var(--muted) transparent` (Firefox / the
    standard property).
  - `::-webkit-scrollbar` (10px), `::-webkit-scrollbar-track { background: transparent }`,
    `::-webkit-scrollbar-thumb { background: var(--muted); border-radius: 5px }`, and a
    `:hover` thumb of `var(--text)` (Chromium / WebKit).
  - Because both read theme vars, the existing `[data-theme="light"]` override recolors the
    scrollbar for free — no second rule set, no JS, no per-theme duplication.

### Tests added

- `tests/unit/test_api_static.py::test_static_app_css_scrollbars_are_theme_aware` — asserts
  the served `app.css` carries `scrollbar-color: var(--muted) transparent` and a
  `::-webkit-scrollbar-thumb` rule whose `background` is `var(--muted)` with a `border-radius`.
- Full `test_api_static.py` green: **64 passed**.

### Gotchas

- **Thumb color is `--muted`, not `--border`, on purpose.** The first attempt used
  `--border` for the thumb, which tripped the existing a11y guard
  `test_static_app_css_separators_use_muted_not_border_for_text` — that test forbids
  `color: var(--border)` anywhere (the substring lives inside `scrollbar-color: var(--border)`),
  because `--border` (#2d3148) is a ~1.3:1 foreground and the project already banned it as a
  foreground color for separators. A scrollbar thumb **is** a foreground UI element over the
  track, so `--muted` (~6.6:1) is the correct, contrast-consistent choice — and it matches the
  conventional light-gray-thumb look (GitHub / macOS dark scrollbars). The failing guard was a
  correct catch, not an obstacle.

### Commits

- `feat: theme-aware scrollbars for dark mode`
