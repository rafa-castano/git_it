import os
from pathlib import Path

from git_it.repository_ingestion.application.advisory_summarizer import AdvisorySummarizer
from git_it.repository_ingestion.application.analysis_service import RepositoryAnalysisService
from git_it.repository_ingestion.application.commit_analysis_service import CommitAnalysisService
from git_it.repository_ingestion.application.commit_query_service import (
    RepositoryCommitQueryService,
)
from git_it.repository_ingestion.application.discussion_summarizer import DiscussionSummarizer
from git_it.repository_ingestion.application.embedding_backfill_service import (
    EmbeddingBackfillService,
)
from git_it.repository_ingestion.application.embedding_service import EmbeddingService
from git_it.repository_ingestion.application.narrative_service import NarrativeService
from git_it.repository_ingestion.application.pattern_detection_service import (
    PatternDetectionService,
)
from git_it.repository_ingestion.application.ports import (
    CommitAnalysisClient,
    CommitAnalysisReader,
    CommitExtractor,
    CommitFactWriter,
    DefaultBranchReader,
    DefaultBranchWriter,
    FileFactWriter,
    FileTreeReader,
    FileTreeWriter,
    LLMClient,
    ProjectDocReader,
    ProjectDocWriter,
)
from git_it.repository_ingestion.application.refresh_all_service import RefreshAllService
from git_it.repository_ingestion.application.release_summarizer import ReleaseSummarizer
from git_it.repository_ingestion.application.service import RepositoryIngestionService
from git_it.repository_ingestion.infrastructure.commits import (
    GitPythonCommitExtractor,
    GitPythonDefaultBranchReader,
    GitPythonFileTreeReader,
)
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
    LiteLLMEmbeddingClient,
    LiteLLMLLMClient,
)
from git_it.repository_ingestion.infrastructure.postgres import (
    PostgresAdvisoryEvidenceStore,
    PostgresCaseStudyStore,
    PostgresCommitAnalysisStore,
    PostgresCommitCountReader,
    PostgresCommitReader,
    PostgresCommitStore,
    PostgresCommitWithAnalysisReader,
    PostgresContributorReader,
    PostgresDefaultBranchStore,
    PostgresDiscussionEvidenceStore,
    PostgresEmbeddingStore,
    PostgresFileFactReader,
    PostgresFileFactStore,
    PostgresFileTreeStore,
    PostgresGithubContextCache,
    PostgresIngestionRunStore,
    PostgresProjectDocStore,
    PostgresReleaseEvidenceStore,
    PostgresRepoMetadataStore,
    PostgresRepositoryDeleter,
    PostgresRepositoryListReader,
    PostgresSynopsisStore,
)
from git_it.repository_ingestion.infrastructure.postgres import (
    initialize as postgres_initialize,
)
from git_it.repository_ingestion.infrastructure.project_docs import GitPythonProjectDocReader
from git_it.repository_ingestion.infrastructure.sqlite import (
    SqliteAdvisoryEvidenceStore,
    SqliteCaseStudyStore,
    SqliteCommitAnalysisStore,
    SqliteCommitCountReader,
    SqliteCommitFactStore,
    SqliteCommitReader,
    SqliteCommitWithAnalysisReader,
    SqliteContributorReader,
    SqliteDefaultBranchStore,
    SqliteDiscussionEvidenceStore,
    SqliteEmbeddingStore,
    SqliteFileFactReader,
    SqliteFileFactStore,
    SqliteFileTreeStore,
    SqliteGithubContextCache,
    SqliteIngestionRunStore,
    SqliteProjectDocStore,
    SqliteReleaseEvidenceStore,
    SqliteRepoMetadataStore,
    SqliteRepositoryDeleter,
    SqliteRepositoryListReader,
    SqliteSynopsisStore,
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


def database_is_provisioned(*, project_root: Path) -> bool:
    """Backend-aware replacement for the SQLite ``db_path.exists()`` guard.

    For SQLite the database is provisioned once the file exists. For PostgreSQL
    there is no file to check — reachability is validated by the connection
    itself, which fails loud (spec 014) instead of falling back to SQLite.
    """
    backend, _ = _get_db_backend()
    if backend == "postgres":
        return True
    return (ingestion_workspace_root(project_root) / "git-it.sqlite3").exists()


def build_repository_list_reader(
    *,
    project_root: Path,
) -> SqliteRepositoryListReader | PostgresRepositoryListReader:
    backend, conninfo = _get_db_backend()
    if backend == "postgres":
        return PostgresRepositoryListReader(conninfo)
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    return SqliteRepositoryListReader(db_path)


def build_case_study_store(
    *,
    project_root: Path,
) -> SqliteCaseStudyStore | PostgresCaseStudyStore:
    backend, conninfo = _get_db_backend()
    if backend == "postgres":
        return PostgresCaseStudyStore(conninfo)
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    store = SqliteCaseStudyStore(db_path)
    store.initialize()
    return store


def build_case_study_reader(
    *,
    project_root: Path,
) -> SqliteCaseStudyStore | PostgresCaseStudyStore:
    """Backend-aware, read-only case study accessor.

    Unlike ``build_case_study_store``, this never calls ``initialize()``.
    Read-only callers (e.g. the MCP server) must not create the
    ``case_studies`` table as a side effect of a read; a missing table means
    "no case study yet," not "provision it now."
    """
    backend, conninfo = _get_db_backend()
    if backend == "postgres":
        return PostgresCaseStudyStore(conninfo)
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    return SqliteCaseStudyStore(db_path)


def build_repo_metadata_store(
    *,
    project_root: Path,
) -> SqliteRepoMetadataStore | PostgresRepoMetadataStore:
    backend, conninfo = _get_db_backend()
    if backend == "postgres":
        return PostgresRepoMetadataStore(conninfo)
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    store = SqliteRepoMetadataStore(db_path)
    store.initialize()
    return store


def build_default_branch_store(
    *,
    project_root: Path,
) -> SqliteDefaultBranchStore | PostgresDefaultBranchStore:
    backend, conninfo = _get_db_backend()
    if backend == "postgres":
        return PostgresDefaultBranchStore(conninfo)
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    store = SqliteDefaultBranchStore(db_path)
    store.initialize()
    return store


def build_file_tree_store(
    *,
    project_root: Path,
) -> SqliteFileTreeStore | PostgresFileTreeStore:
    backend, conninfo = _get_db_backend()
    if backend == "postgres":
        return PostgresFileTreeStore(conninfo)
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    store = SqliteFileTreeStore(db_path)
    store.initialize()
    return store


def build_project_doc_store(
    *,
    project_root: Path,
) -> SqliteProjectDocStore | PostgresProjectDocStore:
    backend, conninfo = _get_db_backend()
    if backend == "postgres":
        return PostgresProjectDocStore(conninfo)
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    store = SqliteProjectDocStore(db_path)
    store.initialize()
    return store


def build_discussion_evidence_store(
    *,
    project_root: Path,
) -> SqliteDiscussionEvidenceStore | PostgresDiscussionEvidenceStore:
    backend, conninfo = _get_db_backend()
    if backend == "postgres":
        return PostgresDiscussionEvidenceStore(conninfo)
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    store = SqliteDiscussionEvidenceStore(db_path)
    store.initialize()
    return store


def build_release_evidence_store(
    *,
    project_root: Path,
) -> SqliteReleaseEvidenceStore | PostgresReleaseEvidenceStore:
    backend, conninfo = _get_db_backend()
    if backend == "postgres":
        return PostgresReleaseEvidenceStore(conninfo)
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    store = SqliteReleaseEvidenceStore(db_path)
    store.initialize()
    return store


def build_advisory_evidence_store(
    *,
    project_root: Path,
) -> SqliteAdvisoryEvidenceStore | PostgresAdvisoryEvidenceStore:
    backend, conninfo = _get_db_backend()
    if backend == "postgres":
        return PostgresAdvisoryEvidenceStore(conninfo)
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    store = SqliteAdvisoryEvidenceStore(db_path)
    store.initialize()
    return store


def build_embedding_store(
    *,
    project_root: Path,
) -> SqliteEmbeddingStore | PostgresEmbeddingStore:
    backend, conninfo = _get_db_backend()
    if backend == "postgres":
        return PostgresEmbeddingStore(conninfo)
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    store = SqliteEmbeddingStore(db_path)
    store.initialize()
    return store


def build_commit_count_reader(
    *,
    project_root: Path,
) -> SqliteCommitCountReader | PostgresCommitCountReader:
    backend, conninfo = _get_db_backend()
    if backend == "postgres":
        return PostgresCommitCountReader(conninfo)
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    return SqliteCommitCountReader(db_path)


def build_commit_with_analysis_reader(
    *,
    project_root: Path,
) -> SqliteCommitWithAnalysisReader | PostgresCommitWithAnalysisReader:
    backend, conninfo = _get_db_backend()
    if backend == "postgres":
        return PostgresCommitWithAnalysisReader(conninfo)
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    return SqliteCommitWithAnalysisReader(db_path)


def build_contributor_reader(
    *,
    project_root: Path,
) -> SqliteContributorReader | PostgresContributorReader:
    backend, conninfo = _get_db_backend()
    if backend == "postgres":
        return PostgresContributorReader(conninfo)
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    return SqliteContributorReader(db_path)


def build_ingestion_run_store(
    *,
    project_root: Path,
) -> SqliteIngestionRunStore | PostgresIngestionRunStore:
    backend, conninfo = _get_db_backend()
    if backend == "postgres":
        return PostgresIngestionRunStore(conninfo)
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    return SqliteIngestionRunStore(db_path)


def build_repository_deleter(
    *,
    project_root: Path,
) -> SqliteRepositoryDeleter | PostgresRepositoryDeleter:
    backend, conninfo = _get_db_backend()
    if backend == "postgres":
        return PostgresRepositoryDeleter(conninfo)
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    return SqliteRepositoryDeleter(db_path)


def build_repository_ingestion_service(
    *,
    project_root: Path,
    repository_id: str,
    runner: GitCommandRunner | None = None,
    commit_extractor: CommitExtractor | None = None,
    commit_fact_writer: CommitFactWriter | None = None,
    file_fact_writer: FileFactWriter | None = None,
    default_branch_reader: DefaultBranchReader | None = None,
    default_branch_writer: DefaultBranchWriter | None = None,
    file_tree_reader: FileTreeReader | None = None,
    file_tree_writer: FileTreeWriter | None = None,
    project_doc_reader: ProjectDocReader | None = None,
    project_doc_writer: ProjectDocWriter | None = None,
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
    branch_reader = (
        default_branch_reader
        if default_branch_reader is not None
        else GitPythonDefaultBranchReader(cache_path=cache_path)
    )
    branch_writer = (
        default_branch_writer
        if default_branch_writer is not None
        else build_default_branch_store(project_root=project_root)
    )
    tree_reader = (
        file_tree_reader
        if file_tree_reader is not None
        else GitPythonFileTreeReader(cache_path=cache_path)
    )
    tree_writer = (
        file_tree_writer
        if file_tree_writer is not None
        else build_file_tree_store(project_root=project_root)
    )
    doc_reader = (
        project_doc_reader
        if project_doc_reader is not None
        else GitPythonProjectDocReader(cache_path=cache_path)
    )
    doc_writer = (
        project_doc_writer
        if project_doc_writer is not None
        else build_project_doc_store(project_root=project_root)
    )
    return RepositoryIngestionService(
        git_gateway=git_gateway,
        commit_extractor=extractor,
        commit_fact_writer=commit_fact_writer if commit_fact_writer is not None else commit_store,
        file_fact_writer=file_fact_writer if file_fact_writer is not None else file_store,
        repository_id=repository_id,
        run_writer=run_store,
        default_branch_reader=branch_reader,
        default_branch_writer=branch_writer,
        file_tree_reader=tree_reader,
        file_tree_writer=tree_writer,
        project_doc_reader=doc_reader,
        project_doc_writer=doc_writer,
    )


def build_refresh_all_service(
    *,
    project_root: Path,
) -> RefreshAllService:
    """Backend-aware factory for the spec 028 refresh-all service.

    Wires ``build_repository_list_reader`` (enumeration) with a per-repository
    ``RepositoryIngestionService`` factory closure over ``build_repository_ingestion_service``
    -- that builder requires a ``repository_id`` per call (its git cache path and run/commit
    stores are repository-scoped), so ``RefreshAllService`` is given a callable rather than
    one pre-built instance, mirroring how ``_ingest_bg`` builds a fresh service per ingest
    call. This factory never wires any analysis/narrative/summarizer collaborator -- the
    free-only lock (spec 028 Goal 3a) holds structurally, not just by convention.
    """
    list_reader = build_repository_list_reader(project_root=project_root)

    def ingest_service_factory(repository_id: str) -> RepositoryIngestionService:
        return build_repository_ingestion_service(
            project_root=project_root,
            repository_id=repository_id,
        )

    return RefreshAllService(
        repository_list_reader=list_reader,
        ingest_service_factory=ingest_service_factory,
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


def build_commit_analysis_reader(
    *,
    project_root: Path,
) -> CommitAnalysisReader:
    backend, conninfo = _get_db_backend()
    if backend == "postgres":
        postgres_initialize(conninfo)
        return PostgresCommitAnalysisStore(conninfo)
    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    store = SqliteCommitAnalysisStore(db_path)
    store.initialize()
    return store


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

    embedding_client = build_embedding_client()
    embedding_service = EmbeddingService(embedding_client) if embedding_client is not None else None
    embedding_writer = (
        build_embedding_store(project_root=project_root) if embedding_client is not None else None
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
            embedding_service=embedding_service,
            embedding_writer=embedding_writer,
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
        embedding_service=embedding_service,
        embedding_writer=embedding_writer,
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


def build_pattern_detection_service_reader(
    *, project_root: Path, model: str | None = None
) -> PatternDetectionService:
    """Backend-aware, read-only pattern detection service.

    Unlike ``build_pattern_detection_service``, this never calls
    ``initialize()``/``postgres_initialize()`` on the analysis store.
    Read-only callers (e.g. the MCP server) must not create the
    ``commit_analyses`` table (or the wider PostgreSQL schema) as a side
    effect of a read; a missing table means "no analyses yet," not
    "provision it now."
    """
    backend, conninfo = _get_db_backend()
    synthesis_client = InstructorPatternSynthesisAdapter(model=model) if model is not None else None

    if backend == "postgres":
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


def build_embedding_client() -> LiteLLMEmbeddingClient | None:
    """Single source of truth for "is the RAG feature (spec 023) available."

    Every other RAG-dependent call site (embedding computation at analysis
    time, the future ``search_similar_commits`` tool) must check this
    factory's return value and skip/hide entirely when it's ``None``, never
    construct a ``LiteLLMEmbeddingClient`` directly.
    """
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    return LiteLLMEmbeddingClient()


def build_embedding_backfill_service(
    *,
    project_root: Path,
) -> EmbeddingBackfillService:
    """Backend-aware factory for the spec 027 embedding backfill service.

    Mirrors ``build_commit_analysis_service``'s embedding-wiring pattern: the embedder
    is ``None`` (and the service becomes a clean no-op) whenever ``build_embedding_client()``
    returns ``None`` -- i.e. without ``OPENAI_API_KEY``.
    """
    embedding_client = build_embedding_client()
    embedder = EmbeddingService(embedding_client) if embedding_client is not None else None
    embedding_store = build_embedding_store(project_root=project_root)
    return EmbeddingBackfillService(
        commit_analysis_reader=build_commit_analysis_reader(project_root=project_root),
        discussion_evidence_reader=build_discussion_evidence_store(project_root=project_root),
        embedding_reader=embedding_store,
        embedding_writer=embedding_store,
        embedder=embedder,
    )


def build_discussion_summarizer(*, model: str) -> DiscussionSummarizer:
    return DiscussionSummarizer(
        LiteLLMLLMClient(model=model, call_site="discussion_summarization"), model=model
    )


def build_release_summarizer(*, model: str) -> ReleaseSummarizer:
    return ReleaseSummarizer(
        LiteLLMLLMClient(model=model, call_site="release_summarization"), model=model
    )


def build_advisory_summarizer(*, model: str) -> AdvisorySummarizer:
    return AdvisorySummarizer(
        LiteLLMLLMClient(model=model, call_site="advisory_summarization"), model=model
    )


def build_narrative_service(*, project_root: Path, model: str) -> NarrativeService:
    backend, conninfo = _get_db_backend()

    if backend == "postgres":
        postgres_initialize(conninfo)
        pg_store = PostgresCommitAnalysisStore(conninfo)
        pg_case_study_store = PostgresCaseStudyStore(conninfo)
        pg_synopsis_store = PostgresSynopsisStore(conninfo)
        return NarrativeService(
            temporal_reader=pg_store,
            pattern_service=build_pattern_detection_service(project_root=project_root),
            llm_client=LiteLLMLLMClient(
                model=_NARRATIVE_MODEL,
                max_tokens=_NARRATIVE_MAX_TOKENS,
                call_site="narrative_generation",
            ),
            case_study_store=pg_case_study_store,
            synopsis_store=pg_synopsis_store,
            discussion_reader=build_discussion_evidence_store(project_root=project_root),
            project_doc_reader=build_project_doc_store(project_root=project_root),
            release_evidence_reader=build_release_evidence_store(project_root=project_root),
            advisory_evidence_reader=build_advisory_evidence_store(project_root=project_root),
        )

    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    store = SqliteCommitAnalysisStore(db_path)
    store.initialize()
    case_study_store = SqliteCaseStudyStore(db_path)
    case_study_store.initialize()
    synopsis_store = SqliteSynopsisStore(db_path)
    synopsis_store.initialize()
    return NarrativeService(
        temporal_reader=store,
        pattern_service=build_pattern_detection_service(project_root=project_root),
        llm_client=LiteLLMLLMClient(
            model=_NARRATIVE_MODEL,
            max_tokens=_NARRATIVE_MAX_TOKENS,
            call_site="narrative_generation",
        ),
        case_study_store=case_study_store,
        synopsis_store=synopsis_store,
        discussion_reader=build_discussion_evidence_store(project_root=project_root),
        project_doc_reader=build_project_doc_store(project_root=project_root),
        release_evidence_reader=build_release_evidence_store(project_root=project_root),
        advisory_evidence_reader=build_advisory_evidence_store(project_root=project_root),
    )
