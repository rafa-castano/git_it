## Batch 14 — Repository ingestion architecture layers

### Goal

Refactor the repository ingestion package from a flat module layout into explicit internal architecture layers before adding more behavior.

### Source of truth

- Clean/hexagonal architecture principles
- feature-first package boundary around `repository_ingestion`
- existing specs requiring application services, stable ports, local CLI, Git safety, SQLite persistence, and future query/GUI readiness

### Problem found

The previous structure was feature-scoped but internally flat:

```text
repository_ingestion/
  application_service.py
  composition.py
  failure_mapping.py
  safe_git.py
  storage.py
  url_contract.py
  workspace_paths.py
```

That was acceptable while the feature was tiny, but it had started to mix concepts:

- domain policies sat next to infrastructure adapters,
- SQLite storage sat next to URL validation,
- the Git adapter imported `GitGatewayError` from the application service module,
- the CLI lived only as a top-level package module,
- future query/application work would make the flat package harder to navigate.

### Refactor applied

The package now keeps the feature boundary and adds internal layers:

```text
repository_ingestion/
  domain/
    failure_mapping.py
    url_contract.py
  application/
    ports.py
    service.py
  infrastructure/
    git.py
    sqlite.py
    workspace.py
  interfaces/
    cli.py
  composition.py
```

The top-level `git_it.cli` module remains as a thin script entrypoint wrapper for `pyproject.toml` compatibility.

### Examples

Domain code owns pure rules:

```text
parse_repository_url(...)
failure_for_error_code(...)
```

Application code owns use cases and ports:

```text
RepositoryIngestionService
GitGateway
GitGatewayError
```

Infrastructure code implements adapters:

```text
SafeGitGateway
SubprocessGitCommandRunner
SqliteIngestionRunStore
repository_cache_path(...)
```

Interface code owns CLI concerns:

```text
git-it ingest <url>
```

### Tests

Existing behavior tests were updated to import from the new layers.

Added architecture guard tests asserting:

- `domain` does not import application, infrastructure, interfaces, or composition,
- `application` does not import infrastructure, interfaces, or composition.

### Production behavior

No behavior change intended.

This was a structural refactor to preserve dependency direction:

```text
domain <- application <- infrastructure/interfaces
                  ^
                  |
             composition wires adapters
```

### Follow-up

The next behavior batch can continue with query DTOs or service-to-storage wiring using the new layer boundaries instead of adding more code to a flat package.
