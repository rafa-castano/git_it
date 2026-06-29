# Repository Ingestion Progress
One file per batch, organized by feature area.

## Ingestion
- [Batch 1 — Repository URL contract](ingestion/batch-01-repository-url-contract.md)
- [Batch 2 — Failure mapping](ingestion/batch-02-failure-mapping.md)
- [Batch 3 — Workspace path safety](ingestion/batch-03-workspace-path-safety.md)
- [Batch 4 — Application validation boundary](ingestion/batch-04-application-validation-boundary.md)
- [Batch 5 — Valid URL starts clone/fetch lifecycle](ingestion/batch-05-valid-url-starts-clone-fetch.md)
- [Batch 6 — Gateway failure mapping](ingestion/batch-06-gateway-failure-mapping.md)
- [Batch 7 — Known gateway failure coverage](ingestion/batch-07-known-gateway-failure-coverage.md)
- [Batch 8 — Safe Git command planning](ingestion/batch-08-safe-git-command-planning.md)
- [Batch 9 — Safe Git runner boundary](ingestion/batch-09-safe-git-runner-boundary.md)
- [Batch 10 — Subprocess Git runner](ingestion/batch-10-subprocess-git-runner.md)
- [Batch 11 — Repository ingestion composition](ingestion/batch-11-repository-ingestion-composition.md)
- [Batch 12 — Local ingest CLI entrypoint](ingestion/batch-12-local-ingest-cli-entrypoint.md)
- [Batch 13 — SQLite ingestion run store](ingestion/batch-13-sqlite-ingestion-run-store.md)
- [Batch 14 — Repository ingestion architecture layers](ingestion/batch-14-architecture-layers.md)
- [Batch 15 — Ingestion run query DTOs](ingestion/batch-15-ingestion-run-query-dtos.md)
- [Batch 16 — Application ingestion run persistence](ingestion/batch-16-application-ingestion-run-persistence.md)
- [Batch 17 — CLI run ID output](ingestion/batch-17-cli-run-id-output.md)
- [Batch 18 — CLI success output with repository identity](ingestion/batch-18-cli-success-output-repository-identity.md)
- [Batch 19 — Commit extraction port + service wires extractor](ingestion/batch-19-commit-extraction-port.md)
- [Batch 20 — GitPython commit extractor wired into composition](ingestion/batch-20-gitpython-commit-extractor.md)
- [Batch 21 — Commit fact SQLite persistence and idempotent inserted/reused counts](ingestion/batch-21-commit-fact-sqlite-persistence.md)
- [Batch 22 — COMPLETED status + file change extraction and persistence](ingestion/batch-22-completed-status-file-change-extraction.md)
- [Batch 23 — Commit query service and `git-it commits` CLI command](ingestion/batch-23-commit-query-service-cli.md)

## Analysis
- [Batch 24 — Provider-agnostic LLM client and `git-it analyze` command](analysis/batch-24-provider-agnostic-llm-client.md)
- [Batch 25 — structured per-commit analysis (spec 002)](analysis/batch-25-structured-per-commit-analysis.md)
- [Batch 26 — rule-based hotspot pattern detection (spec 003)](analysis/batch-26-rule-based-hotspot-pattern-detection.md)
- [Batch 27 — CommitAnalysis persistence + narrative engine + case-study command](analysis/batch-27-commit-analysis-persistence-narrative-engine.md)

## Patterns
- [Batch 28 — Pattern service linked into narrative engine](patterns/batch-28-pattern-service-linked-narrative.md)
- [Batch 29 — Semantic pattern detection](patterns/batch-29-semantic-pattern-detection.md)
- [Batch 30 — Refactor wave detection and spec 004 narrative structure](patterns/batch-30-refactor-wave-narrative-structure.md)
- [Batch 31 — list-analyses CLI command](patterns/batch-31-list-analyses-cli.md)
- [Batch 32 — Temporal narrative ordering and test growth signal](patterns/batch-32-temporal-ordering-test-growth-signal.md)
- [Batch 33 — Ownership concentration pattern detection](patterns/batch-33-ownership-concentration.md)
- [Batch 34 — Revert signal pattern detection](patterns/batch-34-revert-signal-detection.md)

## Pipeline
- [Batch 35 — Case study persistence and cache](pipeline/batch-35-case-study-persistence-cache.md)
- [Batch 36 — Pipeline run command](pipeline/batch-36-pipeline-run-command.md)
- [Batch 37 — Commit pre-classifier (skip/include/sample)](pipeline/batch-37-commit-pre-classifier.md)
- [Batch 38 — Budget guardrail with `--yes` flag](pipeline/batch-38-budget-guardrail.md)
- [Batch 39 — Repo profile injection](pipeline/batch-39-repo-profile-injection.md)
- [Batch 40 — Chronological ordering and date filters](pipeline/batch-40-chronological-ordering-date-filters.md)
- [Batch 41 — Tiered model routing](pipeline/batch-41-tiered-model-routing.md)
- [Batch 42 — Incremental case study update](pipeline/batch-42-incremental-case-study-update.md)
- [Batch 43 — Parallel async analysis](pipeline/batch-43-parallel-async-analysis.md)

## Patterns
- [Batch 44 — Pattern enrichment with evidence, time range, and confidence](patterns/batch-44-pattern-enrichment-evidence-time-range-confidence.md)
- [Batch 45 — LLM pattern synthesis](patterns/batch-45-llm-pattern-synthesis.md)
- [Batch 46 — Dependency migration and architectural shift detectors](patterns/batch-46-dependency-migration-architectural-shift-detectors.md)

## API
- [Batch 47 — FastAPI REST API foundation](api/batch-47-fastapi-rest-api-foundation.md)
- [Batch 48 — HTML dashboard](api/batch-48-html-dashboard.md)
- [Batch 49 — Visual dashboard with Chart.js](api/batch-49-visual-dashboard-chartjs.md)
- [Batch 50 — Accessibility, tooltips, and UX polish](api/batch-50-accessibility-tooltips-ux-polish.md)
- [Batch 51 — GitHub username extraction and analyze progress indicator](api/batch-51-github-username-analyze-progress.md)
- [Batch 52 — Security hardening](api/batch-52-security-hardening.md)
- [Batch 53 — Quality fixes, observability, and ruff compliance](api/batch-53-quality-observability-ruff.md)
- [Batch 54 — TDD endpoint tests for API routes](api/batch-54-tdd-endpoint-tests.md)
- [Batch 55 — Hexagonal architecture refactor of API routes](api/batch-55-hexagonal-architecture-refactor.md)
- [Batch 56 — Explicit model allowlist and MCP git permissions fix](api/batch-56-model-allowlist-mcp-permissions.md)
- [Batch 57 — Open model selection (any LiteLLM provider)](api/batch-57-open-model-selection.md)
- [Batch 58 — GitHub context enrichment (PR and issue injection)](api/batch-58-github-context-enrichment.md)
- [Batch 59 — GitHub Actions CI workflow and Dockerfile](api/batch-59-ci-cd-pipeline.md)
- [Batch 60 — Frontend repository browser (home view)](api/batch-60-frontend-repository-browser.md)
- [Batch 64 — UI/UX overhaul: 11 fixes including design polish, timeline filters, and Case Study improvements](api/batch-64-ui-ux-fixes-design-polish.md)
- [Batch 65 — UI interactive fixes: chart cross-linking, timeline filter, commit file filter, and `files_changed` API field](api/batch-65-ui-interactive-fixes.md)
- [Batch 66 — Analysis UX improvements, hotspot tightening, and timeline cleanup](api/batch-66-analysis-ux-hotspot-cleanup.md)
- [Batch 67 — Case Study audience levels, section pruning, and timeline reload fix](api/batch-67-case-study-audience-timeline-fixes.md)
- [Batch 68 — Synopsis-based incremental case study context](api/batch-68-synopsis-incremental-case-study.md)
- [Batch 69 — Sonnet case study cost in analyze estimate](api/batch-69-sonnet-case-study-cost-estimate.md)
- [Bug fix — UI fixes, analyze ordering, and audience refactor](api/bugfix-session-ui-and-ordering.md)
- [Batch 73 — Rate limit on the analyze estimate endpoint](api/batch-73-rate-limit-estimate-endpoint.md)

## Analysis
- [Bug fix — commit SHA truncation breaking JOIN queries](analysis/bugfix-commit-sha-truncation.md)

## Evals
- [Batch 61 — Evaluation harness for LLM commit classification accuracy](evals/batch-61-evaluation-harness.md)

## Documentation
- [Batch 62 — MkDocs Material documentation site with CI build check](docs/batch-62-documentation-engine.md)

## Infrastructure
- [Batch 63 — PostgreSQL backend as alternative to SQLite via DATABASE_URL](infrastructure/batch-63-postgresql-migration.md)
