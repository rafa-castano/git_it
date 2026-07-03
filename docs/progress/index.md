# Development Progress

This section tracks every implementation batch from initial repository ingestion through the full analysis pipeline, REST API, UI, infrastructure, and documentation engine. Each batch file records what was built, the tests added, and any key decisions made.

Batches are grouped by feature area.

## Ingestion (Batches 1–23)

Repository URL validation, workspace safety, clone/fetch lifecycle, SQLite persistence, ingestion architecture layers, run query DTOs, CLI run identity output, commit extraction, file change extraction, and commit query CLI support.

## Analysis (Batches 24–27, 88–89; bug fix)

Provider-agnostic LLM client, structured per-commit classification, rule-based hotspot detection, analysis persistence, narrative engine, commit SHA JOIN fix, repo-specific case study openings, and Ask tab answer formatting.

## Patterns (Batches 28–34, 44–46)

Pattern service integration, semantic patterns, refactor wave detection, temporal narrative ordering, test growth signal, ownership concentration, revert signal, pattern enrichment with evidence and confidence, LLM synthesis, and dependency migration/architectural shift detectors.

## Pipeline (Batches 35–43)

Case study persistence and cache, pipeline run command, commit pre-classifier, budget guardrail, repo profile injection, chronological ordering and date filters, tiered model routing, incremental update, and parallel async analysis.

## API (Batches 47–60, 64–69, 73–75, 77–78, 80, 82, 94; bug fix)

FastAPI foundation, HTML dashboard, Chart.js visualization, accessibility/UX polish, GitHub username extraction, security hardening, observability, TDD endpoint tests, hexagonal refactor, model allowlist, open model selection, GitHub context enrichment, CI/CD pipeline, frontend repository browser, UI/UX overhaul, interactive chart cross-linking fixes, analysis UX improvements, synopsis-based incremental case study context, estimate cost improvements, analyze ordering and audience refactor fixes, estimate endpoint rate limiting, centralized constants, route decomposition, integration tests, repository deletion, commit count alignment, PostgreSQL read layer, and GitHub stars/language breakdown.

## Evals (Batch 61)

Evaluation harness for measuring LLM commit classification accuracy.

## Documentation (Batches 62, 83)

MkDocs Material documentation site with CI build check, known limitations, roadmap, and stale documentation index correction.

## Infrastructure (Batches 63, 79, 95; bug fix)

PostgreSQL backend support via `DATABASE_URL`, publish-readiness path and hygiene work, backend-aware persistence composition for CLI and MCP/chat tools, and Postgres synopsis store migration from psycopg2 to psycopg v3.

## UI (Batches 76, 81, 84–87, 90, 92–93)

Frontend asset split, tab hierarchy flattening, Timeline merge into Commits, homepage pattern tag removal, unified tooltips, clear-filters action, empty Case Study generation action, activity chart zoom ladder, donut category multi-select, and resizable repository sidebar.

---

Full batch listing is available in `docs/progress/README.md` in the repository.
