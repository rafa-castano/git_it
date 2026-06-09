# Prompt Contract: Pattern Detection Explanation

## Purpose

Explain detected repository evolution patterns using evidence already produced by deterministic detectors and metrics.

## Inputs

- candidate pattern,
- supporting commits,
- relevant metrics,
- affected components,
- time range,
- limitations.

## Output schema

```yaml
title: string
description: string
pattern_type: string
evidence_commit_shas: list[string]
metrics_used: list[string]
confidence: float
limitations: list[string]
learning_lesson: string
```

## Rule

The LLM may explain and synthesize. It must not be the sole detector of a stored pattern unless the pattern is marked exploratory.
