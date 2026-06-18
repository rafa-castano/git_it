# Git It

**Git It** transforms git history into engineering case studies. Point it at any repository and it mines commits, detects patterns, and generates a structured narrative that explains how the codebase evolved — useful for onboarding, technical reviews, and architectural audits.

## Key features

- **Commit analysis** — LLM-powered classification of every commit by category, risk level, and affected components
- **Pattern detection** — rule-based and semantic detection of hotspots, refactor waves, revert signals, ownership concentration, and more
- **Case study generation** — cohesive engineering narrative from the full commit history
- **REST API** — FastAPI backend with authentication and rate limiting
- **Web dashboard** — interactive Chart.js dashboard with Overview, Commits, Patterns, and Case Study tabs

## Quick start

```bash
# 1. Ingest a repository
uv run git-it ingest https://github.com/your-org/your-repo

# 2. Run the full analysis pipeline
uv run git-it analyze

# 3. Start the API server
uv run uvicorn main:app --reload
```

Then open `http://localhost:8000` to explore the dashboard.
