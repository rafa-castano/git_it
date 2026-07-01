---
name: grill-me-with-docs
description: Transforms a vague feature idea into a complete spec via a questioning protocol before any implementation. Use before creating a new feature, changing architecture, modifying LLM prompts, changing data models, adding security-sensitive functionality, generating user-facing narratives, or introducing external dependencies.
---

# Skill: grill-me-with-docs

## Purpose

Use this skill to transform vague ideas into reliable, professional project documentation before implementation.

This skill aligns human and AI understanding by forcing explicit requirements, assumptions, risks, acceptance criteria, tests, and documentation changes.

## When to use

Use this skill before:

- creating a new feature,
- changing core behavior,
- adding an MCP server,
- changing architecture,
- modifying LLM prompts,
- changing data models,
- adding security-sensitive functionality,
- generating user-facing narratives,
- introducing external dependencies.

## Output required

For each feature, produce:

```md
# Feature Spec: <name>

## Summary

## Problem

## Goals

## Non-goals

## Users

## User stories

## Acceptance criteria

## Domain concepts

## Inputs and outputs

## Evidence requirements

## Failure modes

## Security considerations

## Privacy considerations

## Observability

## Tests required

## Evaluation required

## Documentation impact

## ADR impact

## Open questions
```

## Questioning protocol

Ask questions only when the answer materially changes implementation, architecture, security, tests, or user-visible behavior.

Prioritize questions about:

1. User value.
2. Acceptance criteria.
3. Evidence requirements.
4. Failure behavior.
5. Security constraints.
6. Data model impact.
7. Evaluation strategy.
8. Documentation impact.

## Anti-patterns

Do not:

- produce implementation during clarification,
- accept vague acceptance criteria,
- hide assumptions,
- skip tests,
- skip documentation impact,
- overfit to a single example repository,
- allow unsupported AI interpretations.

## Completion rule

The skill is complete only when a reviewer can write tests from the acceptance criteria without needing the original conversation.
