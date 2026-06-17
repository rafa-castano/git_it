from pydantic import BaseModel, ConfigDict


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


class PatternReportResponse(BaseModel):
    repository_id: str
    hotspots: list[HotspotItem]
    refactor_wave: dict | None
    revert_signal: dict | None
    test_growth_signal: dict | None
    bugfix_recurrences: list[dict]
    ownership_concentrations: list[dict]
    dependency_migrations: list[dict]
    architectural_shifts: list[dict]
    explanations: list[dict]
