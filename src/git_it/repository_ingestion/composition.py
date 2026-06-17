from pathlib import Path

from git_it.repository_ingestion.application.analysis_service import RepositoryAnalysisService
from git_it.repository_ingestion.application.commit_analysis_service import CommitAnalysisService
from git_it.repository_ingestion.application.commit_query_service import (
    RepositoryCommitQueryService,
)
from git_it.repository_ingestion.application.narrative_service import NarrativeService
from git_it.repository_ingestion.application.pattern_detection_service import (
    PatternDetectionService,
)
from git_it.repository_ingestion.application.ports import (
    CommitAnalysisClient,
    CommitExtractor,
    CommitFactWriter,
    FileFactWriter,
    LLMClient,
)
from git_it.repository_ingestion.application.service import RepositoryIngestionService
from git_it.repository_ingestion.infrastructure.commits import GitPythonCommitExtractor
from git_it.repository_ingestion.infrastructure.git import (
    GitCommandRunner,
    SafeGitGateway,
    SubprocessGitCommandRunner,
)
from git_it.repository_ingestion.infrastructure.llm import (
    InstructorCommitAnalysisAdapter,
    LiteLLMLLMClient,
)
from git_it.repository_ingestion.infrastructure.sqlite import (
    SqliteCaseStudyStore,
    SqliteCommitAnalysisStore,
    SqliteCommitFactStore,
    SqliteCommitReader,
    SqliteFileFactReader,
    SqliteFileFactStore,
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
    file_fact_writer: FileFactWriter | None = None,
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
    file_store = SqliteFileFactStore(db_path)
    file_store.initialize()
    extractor = (
        commit_extractor
        if commit_extractor is not None
        else GitPythonCommitExtractor(cache_path=cache_path)
    )
    return RepositoryIngestionService(
        git_gateway=git_gateway,
        commit_extractor=extractor,
        commit_fact_writer=commit_fact_writer if commit_fact_writer is not None else commit_store,
        file_fact_writer=file_fact_writer if file_fact_writer is not None else file_store,
        repository_id=repository_id,
        run_writer=run_store,
    )


def build_repository_commit_query_service(
    *,
    project_root: Path,
) -> RepositoryCommitQueryService:
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    return RepositoryCommitQueryService(reader=SqliteCommitReader(db_path))


def build_repository_analysis_service(
    *,
    project_root: Path,
    model: str,
    llm_client: LLMClient | None = None,
) -> RepositoryAnalysisService:
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    client = llm_client if llm_client is not None else LiteLLMLLMClient(model=model)
    return RepositoryAnalysisService(
        reader=SqliteCommitReader(db_path),
        llm_client=client,
    )


def build_commit_analysis_service(
    *,
    project_root: Path,
    model: str,
    sample_model: str | None = None,
    client: CommitAnalysisClient | None = None,
) -> CommitAnalysisService:
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    analysis_store = SqliteCommitAnalysisStore(db_path)
    analysis_store.initialize()
    case_study_store = SqliteCaseStudyStore(db_path)
    case_study_store.initialize()
    analysis_client = client if client is not None else InstructorCommitAnalysisAdapter(model=model)
    sample_client = (
        InstructorCommitAnalysisAdapter(model=sample_model)
        if sample_model is not None and sample_model != model
        else None
    )
    return CommitAnalysisService(
        reader=SqliteCommitReader(db_path),
        client=analysis_client,
        sample_client=sample_client,
        analysis_writer=analysis_store,
        analysis_reader=analysis_store,
        repo_context_reader=case_study_store,
    )


def build_pattern_detection_service(*, project_root: Path) -> PatternDetectionService:
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    analysis_store = SqliteCommitAnalysisStore(db_path)
    analysis_store.initialize()
    file_fact_reader = SqliteFileFactReader(db_path)
    commit_reader = SqliteCommitReader(db_path)
    return PatternDetectionService(
        reader=file_fact_reader,
        analysis_reader=analysis_store,
        ownership_reader=file_fact_reader,
        commit_summary_reader=commit_reader,
        commit_date_reader=commit_reader,
        file_evidence_reader=file_fact_reader,
    )


def build_narrative_service(*, project_root: Path, model: str) -> NarrativeService:
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    store = SqliteCommitAnalysisStore(db_path)
    store.initialize()
    case_study_store = SqliteCaseStudyStore(db_path)
    case_study_store.initialize()
    return NarrativeService(
        temporal_reader=store,
        pattern_service=build_pattern_detection_service(project_root=project_root),
        llm_client=LiteLLMLLMClient(model=model),
        case_study_store=case_study_store,
    )
