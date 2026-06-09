# Testing Strategy

## Purpose

Testing protects the project from silent regressions in deterministic code and AI-generated behavior.

## Test categories

### Unit tests

Use for:

- parsers,
- mappers,
- validators,
- pattern detectors,
- confidence calculations,
- evidence builders.

### Integration tests

Use for:

- database persistence,
- worker jobs,
- GitHub adapters,
- git mining,
- MCP adapters.

### Golden tests

Use for known repositories or fixture histories where expected analyses are stored.

Golden tests must check:

- commit classification,
- pattern detection,
- evidence coverage,
- narrative structure.

### Evaluation tests

Use for LLM behavior.

Evaluate:

- factuality,
- traceability,
- confidence calibration,
- no unsupported claims,
- educational usefulness,
- prompt injection resistance.

### E2E tests

Use for complete learner workflows:

```text
submit repo → ingest → analyze commits → detect patterns → generate narrative → inspect evidence
```

## TDD rule

For new behavior:

1. Write failing test.
2. Run test and confirm failure.
3. Implement minimal code.
4. Run test and confirm pass.
5. Refactor safely.
