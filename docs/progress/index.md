# Development Progress

This section tracks every implementation batch from initial repository ingestion through the full analysis pipeline, REST API, and documentation engine. Each batch file records what was built, the tests added, and any key decisions made.

Batches are grouped by feature area.

## Ingestion (Batches 1–23)

Repository URL validation, workspace safety, clone/fetch lifecycle, SQLite persistence, and commit extraction.

## Analysis (Batches 24–27)

Provider-agnostic LLM client, structured per-commit classification, analysis persistence, and the narrative engine.

## Patterns (Batches 28–34, 44–46)

Pattern detection service, semantic patterns, refactor wave, ownership concentration, revert signal, pattern enrichment with evidence and confidence, LLM synthesis, and dependency migration/architectural shift detectors.

## Pipeline (Batches 35–43)

Case study persistence, pipeline run command, commit pre-classifier, budget guardrail, repo profile injection, ordering/date filters, tiered model routing, incremental update, and parallel async analysis.

## API (Batches 47–60)

FastAPI foundation, HTML dashboard, Chart.js visualization, accessibility/UX polish, GitHub username extraction, security hardening, observability, TDD endpoint tests, hexagonal refactor, model allowlist, open model selection, GitHub context enrichment, CI/CD pipeline, and frontend repository browser.

## Evals (Batch 61)

Evaluation harness for measuring LLM commit classification accuracy.

## Documentation (Batch 62)

MkDocs Material documentation site with CI build check.

---

Full batch listing is available in `docs/progress/README.md` in the repository.
