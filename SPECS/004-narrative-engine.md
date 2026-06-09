# Spec 004: Narrative Engine

Status: Draft  
Primary agent: AI Development Flow Agent  
Supporting agents: Software Engineering Agent, Quality Agent

## Summary

Generate educational narratives from analyzed commits and detected patterns.

## Goals

- Explain project evolution in phases.
- Connect patterns to lessons.
- Allow drill-down from narrative to evidence.
- Preserve uncertainty.
- Avoid unsupported claims.

## Acceptance criteria

```gherkin
Given a detected pattern with supporting commits
When a narrative is generated
Then the narrative links the lesson to the supporting commits.
```

```gherkin
Given weak evidence
When a narrative is generated
Then the narrative expresses uncertainty and does not overstate intent.
```

```gherkin
Given a generated narrative
When evidence references are inspected
Then each major claim has at least one supporting evidence item or a stated limitation.
```

## Narrative structure

```md
# Repository Evolution Story

## Overview
## Timeline
## Main components through time
## Key mistakes and corrections
## Architectural transitions
## Learning lessons
## Evidence index
## Limitations
```

## Test strategy

- evidence coverage tests,
- unsupported claim detection,
- golden narratives,
- readability checks,
- lesson usefulness rubric.
