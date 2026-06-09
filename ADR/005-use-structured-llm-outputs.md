# ADR 005: Use Structured LLM Outputs

Status: Proposed  
Date: YYYY-MM-DD  
Decision makers: TBD

## Context

Free-form LLM output is hard to test, validate, and persist safely.

## Decision

Use schema-validated structured outputs for all persisted AI analysis.

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
