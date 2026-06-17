## Batch 45 — LLM pattern synthesis

### Goal

Add an LLM synthesis layer to pattern detection. After all rule-based detectors run, pass the `PatternReport` to an LLM that produces a brief educational explanation per detected pattern — "why it matters" and "what engineers can learn from it". The LLM is never the sole source of evidence; it only explains patterns already proven by rule-based detection.

### Examples covered

```text
$ git-it patterns https://github.com/owner/repo --model anthropic/claude-haiku-4-5-20251001

Hotspots ...
...

Educational Insights
====================
[HOTSPOT] src/auth.py
  Why it matters: High churn in authentication code correlates with repeated security fixes...
  Takeaway: Consider extracting the authentication module into a separate, well-tested service.
```

### Tests added

- `tests/unit/test_pattern_synthesis.py` — 9 new tests (synthesis called/skipped, explanations attached, user message structure, `_report_has_patterns` utility)
- New `--model` flag tests in `test_patterns_cli.py`

### Production behavior added

- `domain/patterns.py` — `PatternExplanation` frozen dataclass (`pattern_type`, `pattern_key`, `why_it_matters`, `engineer_takeaway`, `confidence_note`); `PatternReport` gains `explanations: list[PatternExplanation]`
- `application/ports.py` — `PatternSynthesisClient` Protocol added
- `infrastructure/llm.py` — `InstructorPatternSynthesisAdapter` with `_PATTERN_SYNTHESIS_SYSTEM_PROMPT` (security note for untrusted Git data) and `_build_pattern_synthesis_user_message()` helper
- `application/pattern_detection_service.py` — `synthesis_client` optional param; `_report_has_patterns()` guard; `dataclasses.replace()` attaches explanations
- `composition.py` — `build_pattern_detection_service()` gains `model: str | None`; wires adapter when provided
- `interfaces/cli.py` — `patterns` command gains `--model`; `PatternFactory` Protocol updated; `_print_pattern_report` renders "Educational Insights" section

### Gotcha

`PatternFactory` Protocol signature change required updating the inner `_factory()` helper in the existing CLI test — needed `model: str | None` param.

### Commits

- `904b468 feat: add PatternExplanation domain model and PatternSynthesisClient port`
- `ecbfa52 feat: wire LLM pattern synthesis into pattern detection service and cli`

---
