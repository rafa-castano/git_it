# Threat Model

## Assets

- GitHub tokens.
- LLM API keys.
- Database credentials.
- Analyzed repository data.
- Generated analysis outputs.
- User accounts when added.
- Local filesystem workspace.

## Trust boundaries

- User input to API.
- Public GitHub content to ingestion system.
- Repository content to LLM prompts.
- LLM output to application storage.
- MCP tools to external systems.
- Worker sandbox to host system.

## Main threats

- Prompt injection through repository content.
- Accidental execution of untrusted repository code.
- SSRF via external URLs.
- Secret leakage in logs.
- Over-permissive MCP access.
- Dependency supply-chain risk.
- False or unsupported generated claims.
- Denial of service through huge repositories.

## Required mitigations

- Treat repository content as data.
- Restrict workspace access.
- Validate URLs.
- Add repository size and timeout limits.
- Use read-only tokens by default.
- Redact secrets from logs.
- Validate LLM output schemas.
- Require evidence and limitations.
- Scan dependencies.
- Do not execute repository code by default.
