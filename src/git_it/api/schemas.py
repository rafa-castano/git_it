from pydantic import BaseModel, ConfigDict

from git_it.repository_ingestion.application.ports import DEFAULT_AUDIENCE
from git_it.repository_ingestion.infrastructure.llm import DEFAULT_MODEL

# ---------------------------------------------------------------------------
# Pattern sub-type schemas
# ---------------------------------------------------------------------------


class LanguageItem(BaseModel):
    language: str
    bytes: int
    percent: float


class RepoSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    repository_id: str
    canonical_url: str
    status: str
    commit_count: int
    analysis_count: int
    has_case_study: bool
    stars: int | None = None
    languages: list[LanguageItem] = []
    default_branch: str | None = None


class RepoListResponse(BaseModel):
    repos: list[RepoSummary]
    total: int


class CaseStudyResponse(BaseModel):
    repository_id: str
    narrative: str
    commit_count: int
    hotspot_count: int
    generated_at: str | None
    available_audiences: list[str] = []


class CommitSummaryItem(BaseModel):
    sha: str
    message: str
    committed_at: str
    category: str | None
    importance: str | None
    summary: str | None
    summary_beginner: str | None = None
    summary_expert: str | None = None
    affected_components: list[str] = []
    files_changed: list[str] = []


class CommitsResponse(BaseModel):
    repository_id: str
    commits: list[CommitSummaryItem]
    total: int


class HotspotItem(BaseModel):
    file_path: str
    commit_count: int
    churn: int
    confidence: float
    evidence_commit_shas: list[str]
    time_range: list[str] | None


class CategoryCountItem(BaseModel):
    category: str
    count: int


class RefactorWaveSchema(BaseModel):
    commit_count: int
    refactor_ratio: float
    evidence_commit_shas: list[str] = []
    time_range: list[str] | None = None
    confidence: float = 0.0


class RevertSignalSchema(BaseModel):
    revert_count: int
    revert_ratio: float
    evidence_commit_shas: list[str] = []
    time_range: list[str] | None = None
    confidence: float = 0.0


class CommitTestGrowthSignalSchema(BaseModel):
    test_commit_count: int
    bugfix_commit_count: int
    test_to_bugfix_ratio: float
    evidence_commit_shas: list[str] = []
    time_range: list[str] | None = None
    confidence: float = 0.0


class BugfixRecurrenceSchema(BaseModel):
    component: str
    bugfix_commit_count: int
    evidence_commit_shas: list[str] = []
    time_range: list[str] | None = None
    confidence: float = 0.0


class OwnershipConcentrationSchema(BaseModel):
    file_path: str
    author_count: int
    commit_count: int
    evidence_commit_shas: list[str] = []
    time_range: list[str] | None = None
    confidence: float = 0.0


class DependencyMigrationSchema(BaseModel):
    from_dependency: str
    to_dependency: str
    commit_count: int
    evidence_commit_shas: list[str] = []
    time_range: list[str] | None = None
    confidence: float = 0.0


class ArchitecturalShiftSchema(BaseModel):
    shift_type: str
    description: str
    evidence_commit_shas: list[str] = []
    time_range: list[str] | None = None
    confidence: float = 0.0


class PatternExplanationSchema(BaseModel):
    pattern_type: str
    pattern_key: str
    why_it_matters: str
    engineer_takeaway: str
    confidence_note: str = ""


class PatternReportResponse(BaseModel):
    repository_id: str
    hotspots: list[HotspotItem]
    refactor_wave: RefactorWaveSchema | None
    revert_signal: RevertSignalSchema | None
    test_growth_signal: CommitTestGrowthSignalSchema | None
    bugfix_recurrences: list[BugfixRecurrenceSchema]
    ownership_concentrations: list[OwnershipConcentrationSchema]
    dependency_migrations: list[DependencyMigrationSchema]
    architectural_shifts: list[ArchitecturalShiftSchema]
    explanations: list[PatternExplanationSchema]
    category_counts: list[CategoryCountItem] = []


class IngestRequest(BaseModel):
    url: str


class IngestResponse(BaseModel):
    repository_id: str
    canonical_url: str
    status: str


class AnalyzeRequest(BaseModel):
    limit: int = 10
    model: str = DEFAULT_MODEL
    audience: str = DEFAULT_AUDIENCE


class AnalyzeResponse(BaseModel):
    status: str
    limit: int


class AnalyzeEstimateResponse(BaseModel):
    total_commits: int
    analyzed_commits: int
    unanalyzed_commits: int
    estimated_llm_calls: int
    estimated_analysis_cost_usd: float
    estimated_narrative_cost_usd: float
    estimated_cost_usd: float


class AnalyzeStatusResponse(BaseModel):
    running: bool
    done: int
    total: int
    pct: int
    cancel_requested: bool = False
    cancelled: bool = False
    error: str | None = None


class RegenerateRequest(BaseModel):
    audience: str = DEFAULT_AUDIENCE


class RegenStatusResponse(BaseModel):
    running: bool
    audience: str
    error: str | None = None


class ContributorItem(BaseModel):
    author_name: str
    commit_count: int
    first_commit: str | None
    last_commit: str | None
    is_bot: bool
    category_counts: dict[str, int]
    top_files: list[str]
    active_days: int
    github_username: str | None = None


class ContributorsResponse(BaseModel):
    repository_id: str
    contributors: list[ContributorItem]
    total: int


class DeleteRepoResponse(BaseModel):
    deleted: bool
    repository_id: str


# ---------------------------------------------------------------------------
# GitItGPT chat (spec 012)
# ---------------------------------------------------------------------------

# Cap on prior turns accepted per request, to bound prompt size / budget.
MAX_CHAT_HISTORY = 20


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatTurn] = []


class ChatResponse(BaseModel):
    reply: str


# ---------------------------------------------------------------------------
# Semantic search (spec 023) -- search_similar_commits chat tool
# ---------------------------------------------------------------------------


class SimilaritySearchResult(BaseModel):
    source_type: str
    evidence_ref: str
    summary_text: str
    score: float


class SimilaritySearchResponse(BaseModel):
    results: list[SimilaritySearchResult] = []


# ---------------------------------------------------------------------------
# Embedding backfill (spec 027)
# ---------------------------------------------------------------------------


class BackfillEmbeddingsStatusResponse(BaseModel):
    available: bool
    missing: int


class BackfillEmbeddingsResponse(BaseModel):
    embedded: int
    already_present: int
    failed: int


# ---------------------------------------------------------------------------
# Refresh all repositories (spec 028)
# ---------------------------------------------------------------------------


class RefreshRepositoryResult(BaseModel):
    repository_id: str
    canonical_url: str
    status: str
    new_commits: int
    error_code: str | None = None
    safe_message: str | None = None


class RefreshAllResponse(BaseModel):
    total_repositories: int
    refreshed_count: int
    failed_count: int
    total_new_commits: int
    repositories: list[RefreshRepositoryResult] = []
