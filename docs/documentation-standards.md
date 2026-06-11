# Documentation Standards

## Purpose

Documentation is part of the product and must remain synchronized with specs, tests, and implementation.

## Required documentation types

- Specs under `specs/`.
- ADRs under `ADR/`.
- Prompt contracts under `docs/prompt-contracts/`.
- Development workflow docs under `docs/`.
- Security docs under `docs/security/`.
- Evaluation docs under `evals/`.

## Style rules

- Prefer clear, direct language.
- Explain why decisions exist, not only what was built.
- Include examples where useful.
- Link to evidence, specs, ADRs, or tests.
- Keep docs close to the behavior they describe.
- Avoid unsupported claims.

## Required sections for feature docs

- Summary.
- User value.
- Behavior.
- Inputs and outputs.
- Evidence requirements.
- Failure behavior.
- Security considerations.
- Tests.
- Related ADRs.

## Documentation quality gate

Before merging:

- relevant docs are updated,
- ADR is added if needed,
- links are valid,
- examples match current behavior,
- generated docs have been reviewed.
