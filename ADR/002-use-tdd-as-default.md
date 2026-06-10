# ADR 002: Use TDD as Default

Status: Proposed  
Date: 2026-06-09
Decision makers: TBD

## Context

Repository analysis and LLM workflows can regress silently.

## Decision

Production behavior must be covered by tests written before or alongside implementation, with failing tests first for new behavior.

## Consequences

### Positive

- Improves reliability and reviewability.
- Supports disciplined AI-assisted development.
- Reduces ambiguity for Codex sessions.

### Negative

- Adds initial process overhead.
- Requires keeping documentation synchronized.

### Neutral

- This decision can be revisited through a superseding ADR.

## Alternatives considered

- Ad hoc implementation.
- Conversation-only memory.
- Tool-specific configuration without repository documentation.

## Security impact

Review security implications before accepting.

## Quality impact

Tests and documentation should enforce the decision.

## Documentation impact

Update related specs and docs.
