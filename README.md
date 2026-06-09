# Git It Codex Starter Kit

This folder contains the Markdown governance layer for developing **Git It** with Codex in VS Code or Codex CLI.

Git It is an educational AI system that analyzes public GitHub repositories at two levels:

1. **Individual commit analysis**: what changed, why it matters, which components were affected, and what evidence supports the interpretation.
2. **Pattern detection**: how the project evolved over time, including mistakes, refactors, recurring problems, architectural transitions, and learning lessons.

## How to use this kit

Copy these files into the root of your local repository before asking Codex to implement anything.

Recommended first Codex prompt:

```text
Read CODEX.md and AGENTS.md.
Then read SPECS/000-template.md and SPECS/001-repository-ingestion.md.
Act as the Quality Agent.
Write the first failing tests for SPECS/001 without implementing production code.
```

## Main rules

- Specifications are the memory of the project.
- Tests are the executable truth of the project.
- Documentation is part of the product.
- AI-generated interpretations must be evidence-grounded.
- Every important architectural decision requires an ADR.
- Do not implement before there is a spec and at least one failing test.
