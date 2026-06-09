# ADR 007: Use Local Git Mining Plus GitHub MCP

Status: Proposed  
Date: YYYY-MM-DD  
Decision makers: TBD

## Context

Full commit history is best mined locally, while GitHub metadata enriches context.

## Decision

Use local git/PyDriller for commit facts and GitHub MCP/API for PRs, issues, releases, and metadata.

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
