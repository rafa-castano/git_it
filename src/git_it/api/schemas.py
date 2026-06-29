from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Pattern sub-type schemas
# ---------------------------------------------------------------------------


class RepoSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    repository_id: str
    canonical_url: str
    status: str
    commit_count: int
    analysis_count: int
    has_case_study: bool


class RepoListResponse(BaseModel):
    repos: list[RepoSummary]
    total: int


class CaseStudyResponse(BaseModel):
    repository_id: str
    narrative: str
    commit_count: int
    hotspot_count: int
    generated_at: str | None


class CommitSummaryItem(BaseModel):
    sha: str
    message: str
    committed_at: str
    category: str | None
    importance: str | None
    summary: str | None
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
    model: str = "anthropic/claude-haiku-4-5-20251001"
    audience: str = "beginner"


class AnalyzeResponse(BaseModel):
    status: str
    limit: int


class AnalyzeEstimateResponse(BaseModel):
    total_commits: int
    analyzed_commits: int
    unanalyzed_commits: int
    estimated_llm_calls: int
    estimated_cost_usd: float


class AnalyzeStatusResponse(BaseModel):
    running: bool
    done: int
    total: int
    pct: int


class RegenerateRequest(BaseModel):
    audience: str = "beginner"


class RegenStatusResponse(BaseModel):
    running: bool
    audience: str


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
