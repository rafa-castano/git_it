# CLAUDE.md
@AGENTS.md
@CODEX.md

This is the single entry point for this project's instruction files. Four files together define how work happens here:

- **`CODEX.md`** — the product constitution: principles, stack, development flow, commit/doc discipline, quality baseline. Imported above.
- **`AGENTS.md`** — subagent routing for git_it's own domain agents (Software Engineering, Architecture, Security, etc. under `.claude/agents/`). Imported above.
- **`CLAUDE.md`** (this file) — the one thing not covered by the other two: the project-specific skill-trigger table below.
- **`.claude/CLAUDE.md`** — gentle-ai-managed (Engram memory protocol, SDD multi-agent orchestrator, review trigger-rules). Not merged into this file on purpose: `gentle-ai sync` owns and rewrites that file by its `<!-- gentle-ai:* -->` markers, so folding its content elsewhere would just have it recreated there on the next sync. Claude Code loads both files together at session start regardless of the physical split.

## Pre-task protocol (mandatory — enforced via UserPromptSubmit hook)

Before implementing ANY task, run this self-check:

| If the task involves...                                             | Read this FIRST                              | Then...                              |
| --------------------------------------------------------------------- | ------------------------------------------- | ------------------------------------ |
| New feature, architecture change, LLM prompt, data model, security   | `.claude/skills/grill-me-with-docs/SKILL.md` | Run questioning protocol, write spec |
| Writing tests, TDD, fixing a bug with a regression test              | `.claude/skills/tdd/SKILL.md`                | Follow the red-green-refactor cycle  |

**Why this exists:** Without this protocol, each session starts cold and jumps directly to implementation, bypassing the skills the project depends on for quality and correctness. The hook injects this reminder automatically; this file documents the intent. The non-negotiables it checks against live in `CODEX.md` (imported above) — not restated here to avoid a second copy going stale.