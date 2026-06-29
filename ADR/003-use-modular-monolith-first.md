# ADR 003: Use Modular Monolith First

Status: Accepted  
Date: 2026-06-09
Decision makers: TBD

## Context

The system has several domains but does not yet need distributed deployment complexity.

## Decision

Start with a modular monolith split into packages. Avoid microservices until operational need is proven.

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
