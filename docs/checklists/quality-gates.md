# Quality Gates

## Local mandatory checks

```bash
ruff check .
ruff format --check .
mypy .
pytest
```

## Recommended CI checks

```bash
pytest tests/integration
pytest tests/golden
python -m evals.run
mkdocs build --strict
```

## AI quality checks

- Output schema is valid.
- Evidence coverage meets threshold.
- Confidence is calibrated.
- Unsupported claims are rejected.
- Prompt injection fixtures do not alter behavior.
- Golden outputs are stable or intentionally updated.
