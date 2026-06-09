# Development Workflow

## Standard workflow

```text
Idea
→ grill-me-with-docs
→ Spec
→ Acceptance criteria
→ ADR if needed
→ Tests
→ Implementation
→ Evaluation
→ Documentation
→ Review
```

## Codex session workflow

1. Ask Codex to read `CODEX.md` and `AGENTS.md`.
2. Select the active subagent.
3. Point Codex to the relevant spec.
4. Ask for tests first.
5. Ask for minimal implementation.
6. Ask for review by Quality, Security, or Architecture as needed.

## Example prompts

```text
Read CODEX.md and AGENTS.md.
Act as the Quality Agent.
Write failing tests for SPECS/001-repository-ingestion.md.
Do not implement production code.
```

```text
Read CODEX.md and AGENTS.md.
Act as the Software Engineering Agent.
Implement only what is needed to pass the tests for SPECS/001.
```

```text
Act as the Security Agent.
Threat model the current repository ingestion implementation.
Check especially prompt injection, filesystem access, URL validation, and accidental code execution.
```
