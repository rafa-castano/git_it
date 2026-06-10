# ADR 004: Separate Facts from Interpretations

Status: Proposed  
Date: 2026-06-09
Decision makers: TBD

## Context

The product analyzes history and may infer intent. Mixing facts with interpretation would reduce trust.

## Decision

Persist raw facts separately from AI-generated interpretations, patterns, lessons, and narratives.

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
