# ADR 005: Use Local-First No-Container MVP Infrastructure

Status: Proposed  
Date: 2026-06-09
Decision makers: TBD

## Context

The project is being developed in a corporate environment with practical constraints around local infrastructure.

Docker Desktop, Kubernetes, privileged machine configuration, unrestricted network access, and long-running local services may be unavailable, blocked, or require approval.

The MVP needs a contributor experience that works from a clean checkout with minimal assumptions while preserving a path toward future deployment.

## Decision

Adopt a local-first, no-container MVP infrastructure strategy.

The default development and test path must not require Docker, Docker Compose, Kubernetes, cloud services, managed databases, or privileged local setup.

Containers and cloud infrastructure remain valid future deployment options, but they are not required for the MVP contributor workflow.

## Consequences

### Positive

- Reduces onboarding friction in restricted corporate environments.
- Keeps the MVP simple, reviewable, and easier to run locally.
- Avoids premature infrastructure complexity.
- Preserves contributor productivity when Docker or cloud access is unavailable.
- Encourages explicit runtime contracts instead of hidden local services.

### Negative

- Some production-like integration scenarios may be deferred.
- Future containerization will require deliberate packaging work.
- Local substitutes may not perfectly match future deployed infrastructure.

### Neutral

- This decision does not prohibit Docker, containers, managed databases, or cloud deployment later.
- Future portability must be achieved through clean boundaries, configuration discipline, and documented runtime contracts.

## Alternatives considered

- Docker Compose as the default local development environment.
- Kubernetes-oriented development from the beginning.
- Managed cloud services for development and evaluation.
- Hybrid setup requiring both local tooling and optional containers.

## Security impact

The local-first approach reduces exposure to unnecessary local services and avoids storing infrastructure secrets in repository files.

Any future deployment path must keep secrets outside images and repository files.

Repository content must continue to be treated as untrusted input.

## Quality impact

The default test suite must run without container dependencies.

Integration tests that require external services must be explicitly marked and excluded from the default contributor path.

Documentation should distinguish required dependencies from optional infrastructure.

## Documentation impact

Update infrastructure agent guidance and any setup documentation that assumes Docker-first development.

Future deployment documentation should explain how containerized or cloud environments map back to the local-first MVP runtime.
