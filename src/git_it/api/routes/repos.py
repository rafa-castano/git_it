import json
import sqlite3
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from git_it.api.deps import get_project_root
from git_it.api.schemas import (
    CaseStudyResponse,
    CommitsResponse,
    CommitSummaryItem,
    HotspotItem,
    PatternReportResponse,
    RepoListResponse,
    RepoSummary,
)
from git_it.repository_ingestion.infrastructure.workspace import ingestion_workspace_root

router = APIRouter(prefix="/api/repos", tags=["repos"])

ProjectRoot = Annotated[Path, Depends(get_project_root)]


def _get_db_path(project_root: Path) -> Path:
    return ingestion_workspace_root(project_root) / "git-it.sqlite3"


# ---------------------------------------------------------------------------
# GET /api/repos
# ---------------------------------------------------------------------------


@router.get("", response_model=RepoListResponse)
def list_repos(project_root: ProjectRoot) -> RepoListResponse:
    db_path = _get_db_path(project_root)
    if not db_path.exists():
        return RepoListResponse(repos=[], total=0)

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                ir.repository_id,
                ir.canonical_url,
                ir.status,
                COUNT(DISTINCT cf.sha)  AS commit_count,
                COUNT(DISTINCT ca.id)   AS analysis_count,
                MAX(CASE WHEN cs.repository_id IS NOT NULL THEN 1 ELSE 0 END) AS has_case_study
            FROM ingestion_runs ir
            LEFT JOIN commit_facts cf ON cf.repository_id = ir.repository_id
            LEFT JOIN commit_analyses ca ON ca.repository_id = ir.repository_id
            LEFT JOIN case_studies cs ON cs.repository_id = ir.repository_id
            GROUP BY ir.repository_id, ir.canonical_url, ir.status
            ORDER BY ir.repository_id
            """
        ).fetchall()

    repos = [
        RepoSummary(
            repository_id=str(row[0]),
            canonical_url=str(row[1]),
            status=str(row[2]),
            commit_count=int(row[3]),
            analysis_count=int(row[4]),
            has_case_study=bool(row[5]),
        )
        for row in rows
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

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT repository_id, narrative, commit_count, hotspot_count, created_at
            FROM case_studies
            WHERE repository_id = ?
            """,
            (repository_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Case study not found")

    return CaseStudyResponse(
        repository_id=str(row[0]),
        narrative=str(row[1]),
        commit_count=int(row[2]),
        hotspot_count=int(row[3]),
        generated_at=str(row[4]) if row[4] is not None else None,
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

    def _dataclass_to_dict(obj: object) -> dict:  # type: ignore[return]
        """Convert a frozen dataclass to a plain dict for JSON serialization."""
        import dataclasses

        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return {k: v for k, v in dataclasses.asdict(obj).items()}  # type: ignore[arg-type]
        return {}

    return PatternReportResponse(
        repository_id=report.repository_id,
        hotspots=hotspots,
        refactor_wave=_dataclass_to_dict(report.refactor_wave) if report.refactor_wave else None,
        revert_signal=_dataclass_to_dict(report.revert_signal) if report.revert_signal else None,
        test_growth_signal=(
            _dataclass_to_dict(report.test_growth_signal) if report.test_growth_signal else None
        ),
        bugfix_recurrences=[_dataclass_to_dict(r) for r in report.bugfix_recurrences],
        ownership_concentrations=[_dataclass_to_dict(r) for r in report.ownership_concentrations],
        dependency_migrations=[_dataclass_to_dict(r) for r in report.dependency_migrations],
        architectural_shifts=[_dataclass_to_dict(r) for r in report.architectural_shifts],
        explanations=[_dataclass_to_dict(e) for e in report.explanations],
    )


# ---------------------------------------------------------------------------
# GET /api/repos/{repository_id}/commits
# ---------------------------------------------------------------------------


@router.get("/{repository_id}/commits", response_model=CommitsResponse)
def get_commits(
    repository_id: str,
    project_root: ProjectRoot,
    limit: int = 20,
    order: str = "newest",
) -> CommitsResponse:
    db_path = _get_db_path(project_root)
    if not db_path.exists():
        return CommitsResponse(repository_id=repository_id, commits=[], total=0)

    order_dir = "ASC" if order == "oldest" else "DESC"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT cf.sha, cf.message, cf.committed_at, ca.data
            FROM commit_facts cf
            LEFT JOIN commit_analyses ca
              ON ca.commit_sha = cf.sha AND ca.repository_id = cf.repository_id
            WHERE cf.repository_id = ?
            ORDER BY cf.committed_at {order_dir}
            LIMIT ?
            """,
            (repository_id, limit),
        ).fetchall()

    commits = []
    for row in rows:
        sha = str(row[0])
        message = str(row[1])
        committed_at = str(row[2])
        category: str | None = None
        importance: str | None = None
        summary: str | None = None

        if row[3] is not None:
            try:
                analysis_data = json.loads(str(row[3]))
                category = analysis_data.get("category")
                importance = analysis_data.get("importance")
                summary = analysis_data.get("summary")
            except (json.JSONDecodeError, AttributeError):
                pass

        commits.append(
            CommitSummaryItem(
                sha=sha,
                message=message,
                committed_at=committed_at,
                category=category,
                importance=importance,
                summary=summary,
            )
        )

    return CommitsResponse(repository_id=repository_id, commits=commits, total=len(commits))
