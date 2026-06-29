import os
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
from git_it.repository_ingestion.infrastructure.github import GithubContextFetcher
from git_it.repository_ingestion.infrastructure.llm import (
    _NARRATIVE_MAX_TOKENS,
    _NARRATIVE_MODEL,
    InstructorCommitAnalysisAdapter,
    InstructorPatternSynthesisAdapter,
    LiteLLMLLMClient,
)
from git_it.repository_ingestion.infrastructure.postgres import (
    PostgresCaseStudyStore,
    PostgresCommitAnalysisStore,
    PostgresCommitReader,
    PostgresCommitStore,
    PostgresFileFactReader,
    PostgresFileFactStore,
    PostgresGithubContextCache,
    PostgresIngestionRunStore,
)
from git_it.repository_ingestion.infrastructure.postgres import (
    initialize as postgres_initialize,
)
from git_it.repository_ingestion.infrastructure.sqlite import (
    SqliteCaseStudyStore,
    SqliteCommitAnalysisStore,
    SqliteCommitFactStore,
    SqliteCommitReader,
    SqliteFileFactReader,
    SqliteFileFactStore,
    SqliteGithubContextCache,
    SqliteIngestionRunStore,
)
from git_it.repository_ingestion.infrastructure.workspace import (
    ingestion_workspace_root,
    repository_cache_path,
)


def _get_db_backend() -> tuple[str, str]:
    """Return (backend_type, connection_string).

    backend_type is 'sqlite' or 'postgres'.
    For SQLite the connection string is empty (callers use db_path instead).
    """
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return "postgres", url
    return "sqlite", ""


def build_repository_ingestion_service(
    *,
    project_root: Path,
    repository_id: str,
    runner: GitCommandRunner | None = None,
    commit_extractor: CommitExtractor | None = None,
    commit_fact_writer: CommitFactWriter | None = None,
    file_fact_writer: FileFactWriter | None = None,
) -> RepositoryIngestionService:
    backend, conninfo = _get_db_backend()
    cache_path = repository_cache_path(project_root, repository_id=repository_id)
    git_gateway = SafeGitGateway(
        cache_path=cache_path,
        runner=SubprocessGitCommandRunner() if runner is None else runner,
    )

    if backend == "postgres":
        postgres_initialize(conninfo)
        run_store: SqliteIngestionRunStore | PostgresIngestionRunStore = PostgresIngestionRunStore(
            conninfo
        )
        commit_store: SqliteCommitFactStore | PostgresCommitStore = PostgresCommitStore(conninfo)
        file_store: SqliteFileFactStore | PostgresFileFactStore = PostgresFileFactStore(conninfo)
    else:
        db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
        sqlite_run_store = SqliteIngestionRunStore(db_path)
        sqlite_run_store.initialize()
        run_store = sqlite_run_store
        sqlite_commit_store = SqliteCommitFactStore(db_path)
        sqlite_commit_store.initialize()
        commit_store = sqlite_commit_store
        sqlite_file_store = SqliteFileFactStore(db_path)
        sqlite_file_store.initialize()
        file_store = sqlite_file_store

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
    backend, conninfo = _get_db_backend()
    if backend == "postgres":
        return RepositoryCommitQueryService(reader=PostgresCommitReader(conninfo))
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    return RepositoryCommitQueryService(reader=SqliteCommitReader(db_path))


def build_repository_analysis_service(
    *,
    project_root: Path,
    model: str,
    llm_client: LLMClient | None = None,
) -> RepositoryAnalysisService:
    backend, conninfo = _get_db_backend()
    client = llm_client if llm_client is not None else LiteLLMLLMClient(model=model)
    if backend == "postgres":
        return RepositoryAnalysisService(
            reader=PostgresCommitReader(conninfo),
            llm_client=client,
        )
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
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
    backend, conninfo = _get_db_backend()
    analysis_client = client if client is not None else InstructorCommitAnalysisAdapter(model=model)
    sample_client = (
        InstructorCommitAnalysisAdapter(model=sample_model)
        if sample_model is not None and sample_model != model
        else None
    )

    if backend == "postgres":
        postgres_initialize(conninfo)
        analysis_store = PostgresCommitAnalysisStore(conninfo)
        case_study_store: SqliteCaseStudyStore | PostgresCaseStudyStore = PostgresCaseStudyStore(
            conninfo
        )
        commit_reader: SqliteCommitReader | PostgresCommitReader = PostgresCommitReader(conninfo)
        github_reader = None
        github_token = os.environ.get("GITHUB_TOKEN")
        if github_token:
            github_cache: SqliteGithubContextCache | PostgresGithubContextCache = (
                PostgresGithubContextCache(conninfo)
            )
            github_reader = GithubContextFetcher(cache=github_cache, token=github_token)
        return CommitAnalysisService(
            reader=commit_reader,
            client=analysis_client,
            sample_client=sample_client,
            analysis_writer=analysis_store,
            analysis_reader=analysis_store,
            repo_context_reader=case_study_store,
            github_context_reader=github_reader,
        )

    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    sqlite_analysis_store = SqliteCommitAnalysisStore(db_path)
    sqlite_analysis_store.initialize()
    sqlite_case_study_store = SqliteCaseStudyStore(db_path)
    sqlite_case_study_store.initialize()
    github_reader = None
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        sqlite_github_cache = SqliteGithubContextCache(db_path)
        sqlite_github_cache.initialize()
        github_reader = GithubContextFetcher(cache=sqlite_github_cache, token=github_token)
    return CommitAnalysisService(
        reader=SqliteCommitReader(db_path),
        client=analysis_client,
        sample_client=sample_client,
        analysis_writer=sqlite_analysis_store,
        analysis_reader=sqlite_analysis_store,
        repo_context_reader=sqlite_case_study_store,
        github_context_reader=github_reader,
    )


def build_pattern_detection_service(
    *, project_root: Path, model: str | None = None
) -> PatternDetectionService:
    backend, conninfo = _get_db_backend()
    synthesis_client = InstructorPatternSynthesisAdapter(model=model) if model is not None else None

    if backend == "postgres":
        postgres_initialize(conninfo)
        pg_analysis_store = PostgresCommitAnalysisStore(conninfo)
        pg_file_reader = PostgresFileFactReader(conninfo)
        pg_commit_reader = PostgresCommitReader(conninfo)
        return PatternDetectionService(
            reader=pg_file_reader,
            analysis_reader=pg_analysis_store,
            ownership_reader=pg_file_reader,
            commit_summary_reader=pg_commit_reader,
            commit_date_reader=pg_commit_reader,
            file_evidence_reader=pg_file_reader,
            synthesis_client=synthesis_client,
        )

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
        synthesis_client=synthesis_client,
    )


def build_narrative_service(*, project_root: Path, model: str) -> NarrativeService:
    backend, conninfo = _get_db_backend()

    if backend == "postgres":
        postgres_initialize(conninfo)
        pg_store = PostgresCommitAnalysisStore(conninfo)
        pg_case_study_store = PostgresCaseStudyStore(conninfo)
        return NarrativeService(
            temporal_reader=pg_store,
            pattern_service=build_pattern_detection_service(project_root=project_root),
            llm_client=LiteLLMLLMClient(model=_NARRATIVE_MODEL, max_tokens=_NARRATIVE_MAX_TOKENS),
            case_study_store=pg_case_study_store,
        )

    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    store = SqliteCommitAnalysisStore(db_path)
    store.initialize()
    case_study_store = SqliteCaseStudyStore(db_path)
    case_study_store.initialize()
    return NarrativeService(
        temporal_reader=store,
        pattern_service=build_pattern_detection_service(project_root=project_root),
        llm_client=LiteLLMLLMClient(model=_NARRATIVE_MODEL, max_tokens=_NARRATIVE_MAX_TOKENS),
        case_study_store=case_study_store,
    )
