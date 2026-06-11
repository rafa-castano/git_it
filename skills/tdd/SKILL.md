---
name: tdd
description: Guides test-driven development with red-green-refactor tracer bullets for Git It. Use when writing tests first, entering the Quality phase, implementing behavior from specs, fixing bugs with regression tests, or when the user mentions TDD, red-green-refactor, failing tests, or test-first development.
---

# Test-Driven Development

## Core rule

Write one failing behavior test before implementation, then add the minimum production code needed to pass it.

Do not write all tests first and then all implementation. That is horizontal slicing. Git It uses vertical tracer bullets:

```text
RED: one behavior test fails
GREEN: minimum code passes that test
REFACTOR: clean up only while green
repeat
```

## Git It priorities

- Specs and ADRs define expected behavior.
- Tests verify public behavior, not private implementation details.
- Prefer integration-style tests through stable application/query/CLI interfaces when practical.
- Keep deterministic unit tests for parsers, mappers, validators, status transitions, and pure policy logic.
- Default tests must not require network access, containers, cloud services, Docker, or live public repositories.
- Repository fixtures must be local and deterministic.
- Security-sensitive behavior needs explicit regression tests.

## Planning checklist

Before writing a test:

- [ ] Identify the authoritative spec or ADR.
- [ ] Select exactly one behavior for the next tracer bullet.
- [ ] Confirm the public interface under test.
- [ ] Define the observable expected outcome.
- [ ] Avoid asserting private functions, internal class names, or storage internals unless the storage contract itself is the behavior.

## RED checklist

For the next test:

- [ ] Test name describes behavior in domain language.
- [ ] Test uses public interfaces or stable ports.
- [ ] Test fails for the right reason.
- [ ] Test does not require network or external services unless explicitly marked integration/network.
- [ ] Test does not execute untrusted repository code.

## GREEN checklist

For the minimum implementation:

- [ ] Add only enough code to pass the current failing test.
- [ ] Do not implement speculative future behavior.
- [ ] Preserve existing docs and ADR decisions.
- [ ] Keep security boundaries intact.

## REFACTOR checklist

Only refactor while tests are green:

- [ ] Remove duplication revealed by the passing tests.
- [ ] Keep public behavior unchanged.
- [ ] Preserve evidence/traceability.
- [ ] Re-run the affected tests after each refactor step.

## Repository ingestion starting point

For `SPECS/001-repository-ingestion.md`, start with the smallest security boundary:

1. URL contract and validation errors.
2. Lifecycle status/error/stage/retryable mapping.
3. Workspace path safety.
4. Local fixture ingestion.
5. Persistence/idempotency.
6. CLI and query DTO contracts.

One tracer bullet at a time. If a test forces a design decision not covered by the spec, stop and update the spec before implementing.
