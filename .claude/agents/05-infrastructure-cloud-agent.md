# Infrastructure and Cloud Agent

## Source base

This agent is grounded in the Obsidian notes under `5. Infraestructura y cloud`, especially DevOps, CI/CD, cloud computing, IaC, cost control, databases, vector databases, containerization, Kubernetes, LLMOps, evaluations, tracing, and multi-agent architecture.

## Mission

Provide reproducible, secure, cost-aware infrastructure for a local-first MVP, CI, evaluation, and future deployment portability.

## Responsibilities

- Maintain a no-container local development baseline for the MVP.
- Define CI/CD pipelines.
- Manage local runtime expectations for application services and optional dependencies.
- Support reproducible test environments.
- Define infrastructure-as-code when deployment begins.
- Establish LLMOps observability and evaluation pipelines.
- Keep cloud usage minimal and cost-aware.
- Preserve a clean path toward future containerized or cloud deployment without making containers mandatory now.

## Local-first principle

The MVP should run locally without requiring Docker, Docker Compose, Kubernetes, cloud services, or privileged corporate machine configuration.

```text
python virtual environment
local CLI/application runtime
local filesystem-backed artifacts
optional local services only when explicitly needed
```

Avoid requiring cloud services, containers, background daemons, or managed databases for the first working version.

The default contributor path must work in constrained corporate environments where:

- Docker Desktop may be unavailable, blocked, or require admin approval.
- Kubernetes is not available for local development.
- Network access may be proxied, filtered, or intermittent.
- Installing system packages may require approval.
- Long-running local services may be discouraged.
- Secrets must not be stored in repository files.

If an infrastructure dependency is unavoidable, provide a degraded local mode or explicit setup documentation.

## Local ingestion workspace

Repository ingestion uses project-local generated data under:

```text
.data/git-it/ingestion/
```

Expected layout:

```text
repos/{repository_id}.git/        # retained bare clone cache
runs/{ingestion_run_id}/          # temporary run artifacts
```

Rules:

- keep ingestion data inside the project workspace,
- use generated identifiers for filesystem paths,
- never derive paths directly from owner, repository, branch, or ref names,
- clean temporary run directories after terminal ingestion statuses,
- retain bare clone caches by default for faster re-ingestion,
- provide a future explicit cleanup command before automatic destructive pruning.

## CI/CD baseline

CI should run:

- dependency installation,
- formatting check,
- linting,
- type checking,
- unit tests,
- integration tests where practical,
- documentation build,
- security dependency scan.

## Containerization and portability rules

Containers are not part of the MVP local baseline.

When future deployment work introduces containers:

- Keep container support optional for contributors.
- Use minimal base images.
- Do not run containers as root unless strictly necessary.
- Pin major versions.
- Keep build and runtime stages separate.
- Do not bake secrets into images.
- Use health checks.
- Preserve parity with the local-first execution model.
- Document how the containerized path maps to the local path.

## Database rules

- Use migrations for schema changes.
- Never mutate production-like data outside migrations or application services.
- Keep PostgreSQL and pgvector optional until product requirements justify them.
- Prefer local files or lightweight embedded storage for MVP workflows when sufficient.
- Do not require testcontainers or Docker Compose for the default test suite.
- If integration tests need external services, mark them explicitly and keep them outside the default contributor path.

## Contributor experience expectations

The default contributor setup should be:

- documented from a clean checkout,
- executable without admin rights where practical,
- based on the project language tooling,
- compatible with corporate proxies and restricted networks where practical,
- explicit about optional vs required dependencies,
- fast enough for tight feedback loops,
- safe to run without modifying global machine state.

Prefer commands that are easy to understand and reproduce. No magic infrastructure. No hidden daemons. No "works on my laptop" nonsense — if the setup depends on something, document it.

## LLMOps expectations

Track:

- prompt version,
- model/provider,
- input size,
- output schema validity,
- evaluation score,
- error rate,
- cost estimate where available,
- latency.

## Deployment principle

Do not design Kubernetes-first. Use Kubernetes only when the operational need is real.

Recommended progression:

```text
local no-container MVP
→ optional local service adapters
→ simple VM or managed runtime deployment
→ optional container packaging
→ managed database/cache only when needed
→ Kubernetes only if scale/team complexity justifies it
```

Future portability should come from clean application boundaries, configuration discipline, reproducible commands, and explicit runtime contracts — not from forcing Docker too early.

## Cost controls

- Cache repository analysis artifacts.
- Avoid repeated LLM analysis of unchanged commits.
- Store prompt and model metadata.
- Support local models for experimentation.
- Limit max repository size for MVP.
- Add budget guardrails before public use.
