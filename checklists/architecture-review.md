# Architecture Review Checklist

- Is the change described in a spec?
- Is an ADR required?
- Are domain and infrastructure concerns separated?
- Are external systems behind adapters?
- Are LLM outputs schema-validated?
- Are raw facts separated from interpretations?
- Is the design simpler than the problem requires?
- Does the change preserve testability?
- Does the change avoid premature microservices?
- Are failure modes explicit?
- Are security boundaries clear?
