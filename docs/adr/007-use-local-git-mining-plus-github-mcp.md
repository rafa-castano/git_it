# ADR 007: Use Local Git Mining Plus GitHub MCP

Status: Accepted  
Date: 2026-06-09
Decision makers: TBD

## Context

Full commit history is best mined locally, while GitHub metadata enriches context.

Repository ingestion must preserve reliable commit and file-change facts even when optional metadata enrichment is temporarily unavailable.

At the same time, missing, private, or inaccessible repositories must fail safely instead of producing ambiguous facts.

## Decision

Use local git/PyDriller for MVP commit, file-change, branch/ref, and tag facts, and use GitHub MCP/API for MVP repository metadata.

PRs, issues, GitHub Releases, release assets, changelog parsing, and richer GitHub metadata are future enrichment sources. They are not part of the MVP repository ingestion path unless specified separately.

For MVP repository ingestion, local Git mining also stores Git tag ref metadata because tags can mark meaningful chapters in repository history.

GitHub Releases, release assets, and changelog parsing remain outside the MVP ingestion path.

For MVP repository ingestion, GitHub API or GitHub MCP is the preferred source for repository metadata:

- owner,
- repo,
- canonical URL,
- default branch,
- fork status when available,
- archived status when available,
- public visibility,
- pushed timestamp when available,
- fetched timestamp.

If GitHub metadata is temporarily unavailable but local clone/fetch succeeds, ingestion may continue with degraded metadata and must record a limitation.

If GitHub metadata confirms the repository is missing, private, or inaccessible, ingestion must fail safely with `FAILED_FETCH`.

Local Git metadata may be used as fallback evidence for default branch detection only when GitHub metadata is temporarily unavailable.

## Consequences

### Positive

- Preserves reliable commit facts even when metadata enrichment has temporary availability issues.
- Keeps Git history mining independent from GitHub-specific metadata details.
- Makes degraded metadata explicit instead of inventing certainty.
- Supports evidence-grounded downstream analysis.

### Negative

- Requires explicit limitation recording for degraded metadata.
- Requires tests that distinguish temporary metadata failures from missing/private/inaccessible repositories.
- Adds adapter boundary complexity between local Git facts and GitHub metadata.

### Neutral

- GitHub metadata enriches ingestion facts but is not the only evidence source for commit history.
- PR, issue, release, and richer metadata ingestion remain future enrichment work outside the MVP repository ingestion path unless specified separately.
- Git tags are repository markers, not proof of release quality, deployment, or operational events.

## Alternatives considered

- Require GitHub metadata before any clone/fetch.
- Ignore GitHub metadata entirely during MVP ingestion.
- Use GitHub API as the source of commit history.
- Treat temporary metadata failure as total ingestion failure.
- Exclude Git tags from MVP ingestion.
- Include full GitHub Releases and release assets in MVP ingestion.

## Security impact

- Use public-read GitHub credentials only.
- Do not log tokens or raw credential-bearing URLs.
- Treat GitHub metadata and repository content as untrusted external input.
- Do not let repository content influence GitHub or MCP tool calls.

## Quality impact

- Tests must cover successful metadata enrichment.
- Tests must cover degraded metadata when metadata fetch is temporarily unavailable but clone/fetch succeeds.
- Tests must cover `FAILED_FETCH` for missing, private, or inaccessible repositories.
- Tests must verify limitations are persisted when metadata is degraded.
- Tests must verify Git tag metadata is persisted without treating tags as deployment evidence.

## Documentation impact

- Keep repository ingestion specs synchronized with the local Git plus GitHub metadata boundary.
- Document degraded metadata behavior and limitations.
