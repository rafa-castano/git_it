import hashlib
import json
import logging
import re
import threading
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request

from git_it.api.auth import require_api_key
from git_it.api.deps import get_project_root
from git_it.api.limiter import limiter
from git_it.api.schemas import (
    AnalyzeEstimateResponse,
    AnalyzeRequest,
    AnalyzeResponse,
    AnalyzeStatusResponse,
    ArchitecturalShiftSchema,
    BugfixRecurrenceSchema,
    CaseStudyResponse,
    CategoryCountItem,
    CommitsResponse,
    CommitSummaryItem,
    CommitTestGrowthSignalSchema,
    ContributorItem,
    ContributorsResponse,
    DependencyMigrationSchema,
    HotspotItem,
    IngestRequest,
    IngestResponse,
    OwnershipConcentrationSchema,
    PatternExplanationSchema,
    PatternReportResponse,
    RefactorWaveSchema,
    RepoListResponse,
    RepoSummary,
    RevertSignalSchema,
)
from git_it.repository_ingestion.composition import (
    build_commit_analysis_service,
    build_repository_ingestion_service,
)
from git_it.repository_ingestion.domain.url_contract import (
    RepositoryUrlValidationError,
    parse_repository_url,
)
from git_it.repository_ingestion.infrastructure.sqlite import (
    SqliteCaseStudyStore,
    SqliteCommitCountReader,
    SqliteCommitWithAnalysisReader,
    SqliteContributorReader,
    SqliteIngestionRunStore,
    SqliteRepositoryListReader,
)
from git_it.repository_ingestion.infrastructure.workspace import ingestion_workspace_root

router = APIRouter(prefix="/api/repos", tags=["repos"])

ProjectRoot = Annotated[Path, Depends(get_project_root)]

_LLM_COST_PER_CALL_USD = 0.0008  # claude-haiku-4-5 approximate cost per analysis call

_logger = logging.getLogger(__name__)


def _extract_github_username(email: str) -> str | None:
    """Extract a GitHub username from a noreply email address."""
    # New noreply format: 12345678+username@users.noreply.github.com
    m = re.match(r"^\d+\+(.+)@users\.noreply\.github\.com$", email or "")
    if m:
        return m.group(1)
    # Old noreply format: username@users.noreply.github.com
    m = re.match(r"^([^@+]+)@users\.noreply\.github\.com$", email or "")
    if m:
        return m.group(1)
    return None


# In-memory progress store: repository_id → {running, done, total}
_analyze_progress: dict[str, dict] = {}
_analyze_progress_lock = threading.Lock()


def _get_db_path(project_root: Path) -> Path:
    return ingestion_workspace_root(project_root) / "git-it.sqlite3"


def _canonical_repo_id(canonical_url: str) -> str:
    return "repo-" + hashlib.sha256(canonical_url.encode()).hexdigest()[:12]


def _normalize_url(raw: str) -> str:
    raw = raw.strip()
    if re.match(r"^[\w.\-]+/[\w.\-]+$", raw):
        return f"https://github.com/{raw}"
    return raw


def _ingest_bg(url: str, project_root: Path) -> None:
    _logger.info("ingestion started", extra={"url": url})
    try:
        parsed = parse_repository_url(url)
        repository_id = _canonical_repo_id(parsed.canonical_url)
        svc = build_repository_ingestion_service(
            project_root=project_root,
            repository_id=repository_id,
        )
        svc.ingest(url)
        _logger.info("ingestion completed", extra={"repository_id": repository_id})
    except Exception as e:
        _logger.warning("ingestion failed: %s", type(e).__name__, extra={"url": url})


# ---------------------------------------------------------------------------
# POST /api/repos/ingest
# ---------------------------------------------------------------------------


@router.post("/ingest", response_model=IngestResponse)
@limiter.limit("5/minute")
def ingest_repo(
    request: Request,
    payload: IngestRequest,
    project_root: ProjectRoot,
    _: None = Depends(require_api_key),
) -> IngestResponse:
    url = _normalize_url(payload.url)
    try:
        parsed = parse_repository_url(url)
    except RepositoryUrlValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.error_code) from exc

    repo_id = _canonical_repo_id(parsed.canonical_url)
    t = threading.Thread(target=_ingest_bg, args=(url, project_root), daemon=True)
    t.start()
    return IngestResponse(
        repository_id=repo_id,
        canonical_url=parsed.canonical_url,
        status="INGESTING",
    )


# ---------------------------------------------------------------------------
# GET /api/repos
# ---------------------------------------------------------------------------


@router.get("", response_model=RepoListResponse)
def list_repos(project_root: ProjectRoot) -> RepoListResponse:
    db_path = _get_db_path(project_root)
    if not db_path.exists():
        return RepoListResponse(repos=[], total=0)

    reader = SqliteRepositoryListReader(db_path)
    records = reader.list_repositories()
    repos = [
        RepoSummary(
            repository_id=r.repository_id,
            canonical_url=r.canonical_url,
            status=r.status,
            commit_count=r.commit_count,
            analysis_count=r.analysis_count,
            has_case_study=r.has_case_study,
        )
        for r in records
    ]
    return RepoListResponse(repos=repos, total=len(repos))


# ---------------------------------------------------------------------------
# GET /api/repos/{repository_id}/case-study
# ---------------------------------------------------------------------------


@router.get("/{repository_id}/case-study", response_model=CaseStudyResponse)
def get_case_study(repository_id: str, project_root: ProjectRoot) -> CaseStudyResponse:
    db_path = _get_db_path(project_root)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="Case study not found")

    store = SqliteCaseStudyStore(db_path)
    record = store.get_case_study(repository_id)

    if record is None:
        raise HTTPException(status_code=404, detail="Case study not found")

    return CaseStudyResponse(
        repository_id=record.repository_id,
        narrative=record.narrative,
        commit_count=record.commit_count,
        hotspot_count=record.hotspot_count,
        generated_at=record.generated_at,
    )


# ---------------------------------------------------------------------------
# GET /api/repos/{repository_id}/patterns
# ---------------------------------------------------------------------------


@router.get("/{repository_id}/patterns", response_model=PatternReportResponse)
def get_patterns(
    repository_id: str,
    project_root: ProjectRoot,
    hotspot_threshold: int = 5,
) -> PatternReportResponse:
    from git_it.repository_ingestion.composition import build_pattern_detection_service

    service = build_pattern_detection_service(project_root=project_root)
    report = service.detect(repository_id, hotspot_threshold=hotspot_threshold)

    hotspots = [
        HotspotItem(
            file_path=h.file_path,
            commit_count=h.commit_count,
            churn=h.churn,
            confidence=h.confidence,
            evidence_commit_shas=list(h.evidence_commit_shas),
            time_range=list(h.time_range) if h.time_range is not None else None,
        )
        for h in report.hotspots
    ]

    refactor_wave = (
        RefactorWaveSchema(
            commit_count=report.refactor_wave.commit_count,
            refactor_ratio=report.refactor_wave.refactor_ratio,
            evidence_commit_shas=list(report.refactor_wave.evidence_commit_shas),
            time_range=(
                list(report.refactor_wave.time_range) if report.refactor_wave.time_range else None
            ),
            confidence=report.refactor_wave.confidence,
        )
        if report.refactor_wave is not None
        else None
    )

    revert_signal = (
        RevertSignalSchema(
            revert_count=report.revert_signal.revert_count,
            revert_ratio=report.revert_signal.revert_ratio,
            evidence_commit_shas=list(report.revert_signal.evidence_commit_shas),
            time_range=(
                list(report.revert_signal.time_range) if report.revert_signal.time_range else None
            ),
            confidence=report.revert_signal.confidence,
        )
        if report.revert_signal is not None
        else None
    )

    test_growth_signal = (
        CommitTestGrowthSignalSchema(
            test_commit_count=report.test_growth_signal.test_commit_count,
            bugfix_commit_count=report.test_growth_signal.bugfix_commit_count,
            test_to_bugfix_ratio=report.test_growth_signal.test_to_bugfix_ratio,
            evidence_commit_shas=list(report.test_growth_signal.evidence_commit_shas),
            time_range=(
                list(report.test_growth_signal.time_range)
                if report.test_growth_signal.time_range
                else None
            ),
            confidence=report.test_growth_signal.confidence,
        )
        if report.test_growth_signal is not None
        else None
    )

    bugfix_recurrences = [
        BugfixRecurrenceSchema(
            component=r.component,
            bugfix_commit_count=r.bugfix_commit_count,
            evidence_commit_shas=list(r.evidence_commit_shas),
            time_range=list(r.time_range) if r.time_range else None,
            confidence=r.confidence,
        )
        for r in report.bugfix_recurrences
    ]

    ownership_concentrations = [
        OwnershipConcentrationSchema(
            file_path=r.file_path,
            author_count=r.author_count,
            commit_count=r.commit_count,
            evidence_commit_shas=list(r.evidence_commit_shas),
            time_range=list(r.time_range) if r.time_range else None,
            confidence=r.confidence,
        )
        for r in report.ownership_concentrations
    ]

    dependency_migrations = [
        DependencyMigrationSchema(
            from_dependency=r.from_dependency,
            to_dependency=r.to_dependency,
            commit_count=r.commit_count,
            evidence_commit_shas=list(r.evidence_commit_shas),
            time_range=list(r.time_range) if r.time_range else None,
            confidence=r.confidence,
        )
        for r in report.dependency_migrations
    ]

    architectural_shifts = [
        ArchitecturalShiftSchema(
            shift_type=r.shift_type,
            description=r.description,
            evidence_commit_shas=list(r.evidence_commit_shas),
            time_range=list(r.time_range) if r.time_range else None,
            confidence=r.confidence,
        )
        for r in report.architectural_shifts
    ]

    explanations = [
        PatternExplanationSchema(
            pattern_type=e.pattern_type,
            pattern_key=e.pattern_key,
            why_it_matters=e.why_it_matters,
            engineer_takeaway=e.engineer_takeaway,
            confidence_note=e.confidence_note,
        )
        for e in report.explanations
    ]

    category_counts = [
        CategoryCountItem(category=cc.category, count=cc.count) for cc in report.category_counts
    ]

    return PatternReportResponse(
        repository_id=report.repository_id,
        hotspots=hotspots,
        refactor_wave=refactor_wave,
        revert_signal=revert_signal,
        test_growth_signal=test_growth_signal,
        bugfix_recurrences=bugfix_recurrences,
        ownership_concentrations=ownership_concentrations,
        dependency_migrations=dependency_migrations,
        architectural_shifts=architectural_shifts,
        explanations=explanations,
        category_counts=category_counts,
    )


# ---------------------------------------------------------------------------
# GET /api/repos/{repository_id}/commits
# ---------------------------------------------------------------------------


@router.get("/{repository_id}/commits", response_model=CommitsResponse)
def get_commits(
    repository_id: str,
    project_root: ProjectRoot,
    limit: int = 20,
    order: Literal["newest", "oldest"] = "newest",
) -> CommitsResponse:
    db_path = _get_db_path(project_root)
    if not db_path.exists():
        return CommitsResponse(repository_id=repository_id, commits=[], total=0)

    reader = SqliteCommitWithAnalysisReader(db_path)
    records = reader.list_commits_with_analyses(repository_id, limit=limit, order=order)

    commits = []
    for record in records:
        category: str | None = None
        importance: str | None = None
        summary: str | None = None
        affected_components: list[str] = []

        if record.analysis_data is not None:
            try:
                analysis_data = json.loads(record.analysis_data)
                category = analysis_data.get("category")
                importance = analysis_data.get("risk_level")
                summary = analysis_data.get("summary")
                raw_ac = analysis_data.get("affected_components") or []
                affected_components = [str(x) for x in raw_ac] if isinstance(raw_ac, list) else []
            except (json.JSONDecodeError, AttributeError):
                pass

        commits.append(
            CommitSummaryItem(
                sha=record.sha,
                message=record.message,
                committed_at=record.committed_at,
                category=category,
                importance=importance,
                summary=summary,
                affected_components=affected_components,
            )
        )

    return CommitsResponse(repository_id=repository_id, commits=commits, total=len(commits))


# ---------------------------------------------------------------------------
# POST /api/repos/{repository_id}/analyze
# ---------------------------------------------------------------------------


def _resolve_canonical_url(repository_id: str, project_root: Path) -> str | None:
    """Look up the canonical_url for a repository from the most recent ingestion run."""
    db_path = _get_db_path(project_root)
    if not db_path.exists():
        return None
    store = SqliteIngestionRunStore(db_path)
    runs = store.list_ingestion_runs_for_repository(repository_id)
    if not runs:
        return None
    return runs[-1].canonical_url


def _analyze_bg(repository_id: str, limit: int, model: str, project_root: Path) -> None:
    _logger.info("analysis started", extra={"repository_id": repository_id})
    with _analyze_progress_lock:
        _analyze_progress[repository_id] = {"running": True, "done": 0, "total": 0}

    def _on_progress(done: int, total: int) -> None:
        with _analyze_progress_lock:
            _analyze_progress[repository_id] = {"running": True, "done": done, "total": total}

    try:
        canonical_url = _resolve_canonical_url(repository_id, project_root)
        svc = build_commit_analysis_service(
            project_root=project_root,
            model=model,
        )
        svc.analyze_commits(
            repository_id,
            limit=limit,
            order="newest",
            on_progress=_on_progress,
            canonical_url=canonical_url,
        )
        _logger.info("analysis completed", extra={"repository_id": repository_id})
    except Exception as e:
        _logger.warning(
            "analysis failed: %s", type(e).__name__, extra={"repository_id": repository_id}
        )
    finally:
        with _analyze_progress_lock:
            prev = _analyze_progress.get(repository_id, {})
            _analyze_progress[repository_id] = {
                "running": False,
                "done": prev.get("done", 0),
                "total": prev.get("total", 0),
            }


@router.get("/{repository_id}/analyze/estimate", response_model=AnalyzeEstimateResponse)
def estimate_analyze(
    repository_id: str,
    project_root: ProjectRoot,
    limit: int = 20,
    model: str = "anthropic/claude-haiku-4-5-20251001",
) -> AnalyzeEstimateResponse:
    db_path = _get_db_path(project_root)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="Repository not found.")
    count_reader = SqliteCommitCountReader(db_path)
    total_commits = count_reader.count_commits(repository_id)
    analyzed_commits = count_reader.count_analyses(repository_id)
    svc = build_commit_analysis_service(project_root=project_root, model=model)
    estimated_llm_calls = svc.estimate_llm_calls(repository_id, limit=limit, order="newest")
    return AnalyzeEstimateResponse(
        total_commits=total_commits,
        analyzed_commits=analyzed_commits,
        unanalyzed_commits=max(0, total_commits - analyzed_commits),
        estimated_llm_calls=estimated_llm_calls,
        estimated_cost_usd=round(estimated_llm_calls * _LLM_COST_PER_CALL_USD, 4),
    )


@router.post("/{repository_id}/analyze", response_model=AnalyzeResponse)
@limiter.limit("10/minute")
def trigger_analyze(
    request: Request,
    repository_id: str,
    payload: AnalyzeRequest,
    project_root: ProjectRoot,
    _: None = Depends(require_api_key),
) -> AnalyzeResponse:
    db_path = _get_db_path(project_root)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="Repository not found.")
    t = threading.Thread(
        target=_analyze_bg,
        args=(repository_id, payload.limit, payload.model, project_root),
        daemon=True,
    )
    t.start()
    return AnalyzeResponse(status="ANALYZING", limit=payload.limit)


@router.get("/{repository_id}/analyze/status", response_model=AnalyzeStatusResponse)
def get_analyze_status(repository_id: str) -> AnalyzeStatusResponse:
    with _analyze_progress_lock:
        p = _analyze_progress.get(repository_id)
    if p is None:
        return AnalyzeStatusResponse(running=False, done=0, total=0, pct=0)
    total = p["total"]
    done = p["done"]
    pct = round(done / total * 100) if total > 0 else 0
    return AnalyzeStatusResponse(running=p["running"], done=done, total=total, pct=pct)


# ---------------------------------------------------------------------------
# GET /api/repos/{repository_id}/contributors
# ---------------------------------------------------------------------------


@router.get("/{repository_id}/contributors", response_model=ContributorsResponse)
def get_contributors(repository_id: str, project_root: ProjectRoot) -> ContributorsResponse:
    db_path = _get_db_path(project_root)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="Repository not found.")

    reader = SqliteContributorReader(db_path)
    records = reader.list_contributors(repository_id)

    if not records:
        raise HTTPException(status_code=404, detail="No commits found for this repository.")

    contributors = [
        ContributorItem(
            author_name=r.author_name,
            commit_count=r.commit_count,
            first_commit=r.first_commit,
            last_commit=r.last_commit,
            is_bot=r.is_bot,
            active_days=r.active_days,
            category_counts=r.category_counts,
            top_files=r.top_files,
            github_username=r.github_username,
        )
        for r in records
    ]

    return ContributorsResponse(
        repository_id=repository_id,
        contributors=contributors,
        total=len(contributors),
    )
