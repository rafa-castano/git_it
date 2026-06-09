# Spec 003: Pattern Detection

Status: Draft  
Primary agent: Software Engineering Agent  
Supporting agents: Architecture Agent, Quality Agent, AI Development Flow Agent

## Summary

Detect higher-level evolution patterns from commit analyses, raw metrics, file changes, and temporal clustering.

## Goals

Detect patterns such as:

- recurring bugfixes,
- refactor waves,
- component birth and extraction,
- architectural shifts,
- test growth after regressions,
- dependency migrations,
- performance improvement cycles,
- technical debt repayment,
- rollback/revert sequences,
- hotspots and ownership concentration.

## Non-goals

- Generating final educational narratives.
- Claiming the team planned a change unless evidence supports it.

## Acceptance criteria

```gherkin
Given repeated modifications to the same component over time
When pattern detection runs
Then the system may identify a hotspot pattern with supporting commits and metrics.
```

```gherkin
Given several commits that extract logic into new modules
When pattern detection runs
Then the system may identify a component extraction or refactor wave pattern.
```

```gherkin
Given a detected pattern
When it is stored
Then it includes evidence commits, metrics, confidence, limitations, and time range.
```

## Detection strategy

Use three layers:

1. Rule-based detectors for explicit signals.
2. Statistical detectors for temporal and churn patterns.
3. LLM synthesis for explanation, never as the sole source of evidence.

## Test strategy

- unit tests for each detector,
- fixture repositories with known patterns,
- golden output tests,
- false positive tests,
- confidence threshold tests.
