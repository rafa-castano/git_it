from pathlib import Path

from git_it.repository_ingestion.application.ports import CommitExtractor, CommitFactWriter
from git_it.repository_ingestion.application.service import RepositoryIngestionService
from git_it.repository_ingestion.infrastructure.commits import GitPythonCommitExtractor
from git_it.repository_ingestion.infrastructure.git import (
    GitCommandRunner,
    SafeGitGateway,
    SubprocessGitCommandRunner,
)
from git_it.repository_ingestion.infrastructure.sqlite import (
    SqliteCommitFactStore,
    SqliteIngestionRunStore,
)
from git_it.repository_ingestion.infrastructure.workspace import (
    ingestion_workspace_root,
    repository_cache_path,
)


def build_repository_ingestion_service(
    *,
    project_root: Path,
    repository_id: str,
    runner: GitCommandRunner | None = None,
    commit_extractor: CommitExtractor | None = None,
    commit_fact_writer: CommitFactWriter | None = None,
) -> RepositoryIngestionService:
    cache_path = repository_cache_path(project_root, repository_id=repository_id)
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    git_gateway = SafeGitGateway(
        cache_path=cache_path,
        runner=SubprocessGitCommandRunner() if runner is None else runner,
    )
    run_store = SqliteIngestionRunStore(db_path)
    run_store.initialize()
    commit_store = SqliteCommitFactStore(db_path)
    commit_store.initialize()
    extractor = (
        commit_extractor
        if commit_extractor is not None
        else GitPythonCommitExtractor(cache_path=cache_path)
    )
    writer = commit_fact_writer if commit_fact_writer is not None else commit_store
    return RepositoryIngestionService(
        git_gateway=git_gateway,
        commit_extractor=extractor,
        commit_fact_writer=writer,
        repository_id=repository_id,
        run_writer=run_store,
    )
