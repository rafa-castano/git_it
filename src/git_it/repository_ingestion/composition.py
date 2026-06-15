from pathlib import Path

from git_it.repository_ingestion.application.service import RepositoryIngestionService
from git_it.repository_ingestion.infrastructure.git import (
    GitCommandRunner,
    SafeGitGateway,
    SubprocessGitCommandRunner,
)
from git_it.repository_ingestion.infrastructure.sqlite import SqliteIngestionRunStore
from git_it.repository_ingestion.infrastructure.workspace import (
    ingestion_workspace_root,
    repository_cache_path,
)


def build_repository_ingestion_service(
    *,
    project_root: Path,
    repository_id: str,
    runner: GitCommandRunner | None = None,
) -> RepositoryIngestionService:
    cache_path = repository_cache_path(project_root, repository_id=repository_id)
    git_gateway = SafeGitGateway(
        cache_path=cache_path,
        runner=SubprocessGitCommandRunner() if runner is None else runner,
    )
    run_store = SqliteIngestionRunStore(ingestion_workspace_root(project_root) / "git-it.sqlite3")
    run_store.initialize()
    return RepositoryIngestionService(
        git_gateway=git_gateway,
        repository_id=repository_id,
        run_writer=run_store,
    )
