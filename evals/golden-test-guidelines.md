# Golden Test Guidelines

## Purpose

Golden tests protect expected AI and analysis behavior across changes.

## Fixture repository requirements

Each fixture should include:

- known commit history,
- expected commit classifications,
- expected patterns,
- expected limitations,
- expected narrative outline.

## Update policy

Golden outputs may be updated only when:

- the spec changes,
- an ADR changes expected behavior,
- a bug is fixed and the old output was wrong.

Every golden update must explain why the change is intentional.

## Minimum golden cases

- Small feature addition.
- Bugfix sequence.
- Refactor wave.
- Test growth after regressions.
- Dependency migration.
- Prompt injection attempt in commit message.
