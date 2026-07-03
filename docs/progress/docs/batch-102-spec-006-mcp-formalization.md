## Batch 102 — Formalize spec 006 (MCP strategy) into a governance spec

### Goal

`specs/006-mcp-strategy.md` was a thin Draft: a bullet list of "recommended"
MCP servers and three Gherkin scenarios that were not concretely checkable
(e.g. "its allowed operations, permissions, and security risks are
documented" — documented where, checked how?). Meanwhile the actual operative
MCP governance already existed in `AGENTS.md` ("MCP Usage Policy", "Git MCP
policy") and `docs/mcp/security.md`. This batch closes that gap: it turns
spec 006 into a concrete governance spec with testable acceptance criteria
that anchor (not duplicate or contradict) the existing `AGENTS.md` policy,
and fills in the previously-empty `docs/mcp/setup.md`. No production code
changes — this is a docs-only batch, consistent with a decision already made:
Git It as MCP **consumer** (spec 006) is not deferred to spec 011; spec 011
(`specs/011-mcp-server-exposure.md`, Implemented) is the separate, already
implemented **provider**-side inverse.

### What was added

**`specs/006-mcp-strategy.md`** — rewritten from Draft to `Status: Implemented`
(matching spec 011's status for consumer/provider symmetry). Adds:

- A Problem section explaining the drift between the vague old spec and the
  concrete policy already enforced via `AGENTS.md`.
- Seven testable acceptance criteria (AC-1 through AC-7) covering: every
  configured server being documented in `docs/mcp/`; Git MCP exposing no
  write path; Filesystem MCP scoped to non-secret workspace subdirectories;
  PostgreSQL MCP defaulting to read-only; repository content never
  controlling tool calls (prompt-injection boundary, tied to ADR 008); the
  spec 011 cross-reference being explicit and non-duplicative; and any future
  scope expansion requiring documented justification.
- An explicit "Domain concepts" table distinguishing MCP consumer vs
  provider.
- Cross-references to `AGENTS.md` (operative policy source, not restated
  verbatim), ADR 007 (local Git mining + GitHub MCP), and ADR 008 (treat
  repository content as untrusted) instead of introducing a new ADR.
- An "Out of scope" section explicitly excluding spec 011, automated CI
  enforcement of MCP config, and networked/remote MCP transports.

**`docs/mcp/setup.md`** (was empty, 0 bytes) — filled in with concrete
least-privilege setup guidance per server (Filesystem, Git, GitHub,
PostgreSQL, Context7/Exa, Playwright MCP), token/secret handling via
environment variables, and a checklist for verifying a new or widened MCP
server against `docs/mcp/security.md` and spec 006 AC-7.

### Tests added

None — docs-only change (`CODEX.md`: TDD does not apply to trivial
documentation-only changes). Validated with
`uv run --group docs mkdocs build --strict`.

### Gotchas

- **`docs/specs/index.md` still lists spec 006 as "Draft"** (row 16). This
  batch's explicit file scope was `specs/006-mcp-strategy.md`,
  `docs/mcp/setup.md`, this progress doc, and `docs/progress/README.md` —
  updating the spec index table was intentionally left out of scope to keep
  the commit minimal and matching the requested file list. The index is
  already independently stale in other ways (missing rows for specs
  015–021), so a follow-up batch should refresh the whole table rather than
  patch one row in isolation.
- **Out-of-tree links bite again.** As documented in batch 83, `mkdocs.yml`
  sets `docs_dir: docs`, so `mkdocs build --strict` cannot resolve Markdown
  links pointing to `specs/` or `ADR/` (outside the docs tree). Every
  reference to `specs/006-mcp-strategy.md`, `specs/011-mcp-server-exposure.md`,
  `AGENTS.md`, and `ADR/*.md` in the new spec text and in `docs/mcp/setup.md`
  is written as plain backtick text, not a Markdown link, matching the
  established convention.
- **Status convention checked, not assumed.** House convention mixes
  `Accepted` (approved-and-built specs like 001–004, 007, 014–020) and
  `Implemented` (008, 011, 012, 013, 021). Since spec 011 — the provider-side
  counterpart — uses `Implemented`, and spec 006's governance is already
  actively enforced via `AGENTS.md` (not merely "approved"), `Implemented`
  was chosen for consistency with 011 rather than defaulting to `Accepted`.

### Commits

- `docs: formalize spec 006 MCP strategy into governance spec`
