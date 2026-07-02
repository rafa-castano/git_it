# Architectural Decision Records

ADRs record significant architectural choices made during Git It development. Each ADR captures the context, the decision, and the rationale so that future contributors understand why the system is structured the way it is.

ADR source files live in `ADR/` at the project root.

## ADR index

ADR source files live in `ADR/` at the project root. The table below lists all current ADRs.

| ADR | Title | Status |
|---|---|---|
| 001 | Use Spec-Driven Development | Accepted |
| 002 | Use TDD as Default | Accepted |
| 003 | Use Modular Monolith First | Accepted |
| 004 | Separate Facts from Interpretations | Accepted |
| 005 | Use Local-First No-Container MVP Infrastructure | Accepted |
| 006 | Use SQLite for MVP, PostgreSQL+pgvector for Future | Accepted |
| 007 | Use Local Git Mining Plus GitHub MCP | Accepted |
| 008 | Treat Repository Content as Untrusted | Accepted |
| 009 | Process Not-Yet-Analyzed Commits Oldest-First | Accepted |
| 010 | Accepted Limitations of the Local-First Single-Process MVP | Accepted |
| 011 | Expose the Git It Domain as a Read-Only MCP Server | Accepted |
| 012 | Introduce In-Process Agentic Tool-Calling (GitItGPT) | Accepted |
| 013 | Sanitize All Client-Side Markdown Rendering with DOMPurify | Accepted |
| 014 | Stream the GitItGPT Final Answer over SSE | Accepted |

## How to add a new ADR

1. Copy `ADR/000-template.md` to `ADR/NNN-short-title.md`.
2. Fill in status, context, decision, and consequences.
3. Link the new ADR from the relevant feature docs and from this index.
4. If the decision affects a spec, reference the ADR from that spec.
