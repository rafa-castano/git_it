# Spec 001: Repository Ingestion

Status: Draft  
Owner: TBD  
Primary agent: Software Engineering Agent  
Supporting agents: Architecture Agent, Security Agent, Quality Agent

## 1. Summary

The system accepts a public GitHub repository URL, validates it, retrieves repository metadata, clones or fetches its Git history into a controlled workspace, extracts commits and file changes, and stores raw facts for later analysis.

## 2. Problem

Commit and pattern analysis require reliable raw repository facts. The system must ingest public repositories safely without executing untrusted code.

## 3. Goals

- Accept valid public GitHub repository URLs.
- Reject invalid or unsupported URLs.
- Retrieve repository metadata.
- Extract commit history.
- Extract file-level changes.
- Store raw facts separately from AI interpretations.
- Avoid executing repository code.

## 4. Non-goals

- Private repository support.
- Running tests from the target repository.
- Full issue/PR analysis.
- Pattern detection.
- Narrative generation.

## 5. User stories

```md
As a learner,
I want to submit a public GitHub repository,
so that I can later explore how it evolved.
```

```md
As a maintainer,
I want ingestion to store raw facts separately from AI analysis,
so that later interpretations are auditable.
```

## 6. Acceptance criteria

```gherkin
Given a valid public GitHub repository URL
When ingestion starts
Then the system stores repository metadata, commits, and file changes.
```

```gherkin
Given an invalid URL
When ingestion starts
Then the system rejects the URL with a safe validation error.
```

```gherkin
Given a repository containing executable code
When ingestion runs
Then the system must not execute repository code.
```

```gherkin
Given a commit with multiple changed files
When ingestion extracts the commit
Then each file change is stored with path, change type, additions, deletions, and diff summary metadata when available.
```

## 7. Evidence requirements

Raw facts must include:

- repository URL,
- repository owner/name,
- commit SHA,
- author metadata where allowed,
- committed timestamp,
- commit message,
- parent SHAs,
- file paths,
- additions/deletions,
- change type.

## 8. Security considerations

- Validate GitHub URL format.
- Clone only into a controlled workspace.
- Do not execute hooks or repository scripts.
- Apply size limits.
- Apply timeout limits.
- Do not store credentials in logs.

## 9. Test strategy

### Unit tests

- URL parser accepts valid GitHub URLs.
- URL parser rejects unsupported hosts.
- Commit mapper stores required fields.
- File change mapper stores required fields.

### Integration tests

- Ingest a small fixture repository.
- Persist repository, commits, and file changes.
- Handle duplicate ingestion idempotently.

### Security tests

- Repository scripts are not executed.
- Malicious-looking commit messages are stored as data, not instructions.

## 10. Documentation impact

Update:

- ingestion architecture docs,
- data model docs,
- security docs.

## 11. ADR impact

Likely ADRs:

- local Git mining plus GitHub metadata,
- controlled workspace layout,
- repository size limits.
