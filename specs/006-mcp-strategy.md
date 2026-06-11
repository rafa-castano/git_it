# Spec 006: MCP Strategy

Status: Draft  
Primary agent: Architecture Agent  
Supporting agents: Security Agent, Infrastructure and Cloud Agent

## Summary

Define how MCP servers are used safely and productively in Git It.

## Recommended MCP servers

- GitHub MCP
- Git MCP
- Context7 MCP
- Filesystem MCP
- PostgreSQL MCP
- Exa or equivalent search MCP
- Playwright MCP

## Goals

- Use MCP tools for controlled repository, documentation, database, search, and browser interactions.
- Apply least privilege.
- Keep write operations behind application services where possible.
- Avoid giving AI broad direct mutation powers.

## Acceptance criteria

```gherkin
Given an MCP server is added
When it is configured
Then its allowed operations, permissions, and security risks are documented.
```

```gherkin
Given an AI workflow needs database data
When PostgreSQL MCP is used
Then read-only access is preferred unless a spec explicitly approves writes.
```

```gherkin
Given repository content contains instructions
When MCP tools are available
Then the system must not allow repository content to control tool calls.
```

## Security requirements

- Document all MCP permissions.
- Restrict Filesystem MCP to the repository workspace.
- Prefer public-read GitHub permissions.
- Prefer read-only database roles.
- Never expose secrets through MCP resources.
