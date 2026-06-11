# Spec 002: Commit-Level Analysis

Status: Draft  
Primary agent: Software Engineering Agent  
Supporting agents: AI Development Flow Agent, Quality Agent, Security Agent

## Summary

Analyze individual commits and produce structured, evidence-grounded interpretations.

## Goals

- Summarize what changed.
- Classify commit type.
- Detect affected components.
- Estimate intent with confidence.
- Identify risk level.
- Preserve evidence references.
- Store limitations.

## Non-goals

- Pattern detection.
- Full narrative generation.
- Claiming developer motivation as fact.

## User stories

```md
As a learner,
I want to understand why a commit matters,
so that I can learn from concrete engineering decisions.
```

```md
As a reviewer,
I want each interpretation to include evidence,
so that I can verify the analysis.
```

## Acceptance criteria

```gherkin
Given an ingested commit
When commit analysis runs
Then the system creates a structured CommitAnalysis with summary, category, affected components, evidence, confidence, and limitations.
```

```gherkin
Given insufficient evidence about intent
When commit analysis runs
Then the system marks intent as inferred and lowers confidence.
```

```gherkin
Given malicious instructions inside a commit message or diff
When commit analysis runs
Then the system treats them as repository data and does not follow them as instructions.
```

## Output schema

```yaml
summary: string
category: feature | bugfix | refactor | test | docs | build | security | performance | chore | unknown
intent: string | null
intent_is_inferred: boolean
affected_components: list[string]
risk_level: low | medium | high | unknown
confidence: float
evidence: list[EvidenceRef]
limitations: list[string]
```

## Test strategy

- schema validation tests,
- prompt injection tests,
- golden tests for known commits,
- confidence calibration tests,
- evidence coverage tests.
