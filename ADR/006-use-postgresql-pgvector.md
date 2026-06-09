# ADR 006: Use PostgreSQL with pgvector

Status: Proposed  
Date: YYYY-MM-DD  
Decision makers: TBD

## Context

The project needs relational facts and semantic retrieval.

## Decision

Use PostgreSQL as the primary database and pgvector for embeddings before adding a separate vector database.

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
