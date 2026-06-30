"""Shared read-only domain tools (spec 012 AC-1).

These plain functions are the single source of truth for the five read-only
operations. `git_it.mcp.server` wraps them as MCP tools; the chat service
(GitItGPT) calls them directly. Each resolves the SQLite DB from ``project_root``
and delegates to the same reader/query classes the REST API uses. Read-only: no
write adapter is imported and no ``initialize()``/``save_*`` path is called.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any

from git_it.api.mappers import map_pattern_report
from git_it.api.schemas import (
    CaseStudyResponse,
    CommitsResponse,
    CommitSummaryItem,
    ContributorItem,
    ContributorsResponse,
    PatternReportResponse,
    RepoListResponse,
    RepoSummary,
)
from git_it.repository_ingestion.application.ports import DEFAULT_AUDIENCE
from git_it.repository_ingestion.infrastructure.sqlite import (
    SqliteCaseStudyStore,
    SqliteCommitWithAnalysisReader,
    SqliteContributorReader,
    SqliteRepositoryListReader,
)
from git_it.repository_ingestion.infrastructure.workspace import ingestion_workspace_root


def db_path_for(project_root: Path) -> Path:
    return ingestion_workspace_root(project_root) / "git-it.sqlite3"


def _empty_patterns(repository_id: str) -> PatternReportResponse:
    return PatternReportResponse(
        repository_id=repository_id,
        hotspots=[],
        refactor_wave=None,
        revert_signal=None,
        test_growth_signal=None,
        bugfix_recurrences=[],
        ownership_concentrations=[],
        dependency_migrations=[],
        architectural_shifts=[],
        explanations=[],
        category_counts=[],
    )


def _commit_item(record: Any) -> CommitSummaryItem:
    """Mirror the REST /commits parsing of the analysis JSON blob."""
    cat: str | None = None
    importance: str | None = None
    summary: str | None = None
    summary_beginner: str | None = None
    summary_expert: str | None = None
    affected_components: list[str] = []

    if record.analysis_data is not None:
        try:
            data = json.loads(record.analysis_data)
            cat = data.get("category")
            importance = data.get("risk_level")
            summary = data.get("summary")
            summary_beginner = data.get("summary_beginner")
            summary_expert = data.get("summary_expert")
            raw_ac = data.get("affected_components") or []
            affected_components = [str(x) for x in raw_ac] if isinstance(raw_ac, list) else []
        except (json.JSONDecodeError, AttributeError):
            pass

    return CommitSummaryItem(
        sha=record.sha,
        message=record.message,
        committed_at=record.committed_at,
        category=cat,
        importance=importance,
        summary=summary,
        summary_beginner=summary_beginner,
        summary_expert=summary_expert,
        affected_components=affected_components,
        files_changed=list(record.files_changed),
    )


def list_repositories(project_root: Path) -> RepoListResponse:
    """List analyzed repositories with id, canonical URL, status, and counts."""
    db_path = db_path_for(project_root)
    if not db_path.exists():
        return RepoListResponse(repos=[], total=0)
    reader = SqliteRepositoryListReader(db_path)
    repos = [
        RepoSummary(
            repository_id=r.repository_id,
            canonical_url=r.canonical_url,
            status=r.status,
            commit_count=r.commit_count,
            analysis_count=r.analysis_count,
            has_case_study=r.has_case_study,
        )
        for r in reader.list_repositories()
    ]
    return RepoListResponse(repos=repos, total=len(repos))


def get_case_study(
    project_root: Path, repository_id: str, audience: str = DEFAULT_AUDIENCE
) -> CaseStudyResponse:
    """Return the stored case study narrative and the available audiences for a
    repository. Read-only: an unavailable audience is reported, never generated."""
    db_path = db_path_for(project_root)
    empty = CaseStudyResponse(
        repository_id=repository_id,
        narrative="",
        commit_count=0,
        hotspot_count=0,
        generated_at=None,
        available_audiences=[],
    )
    if not db_path.exists():
        return empty
    store = SqliteCaseStudyStore(db_path)
    try:
        record = store.get_case_study(repository_id, audience)
        available = store.list_available_audiences(repository_id)
    except sqlite3.OperationalError:
        return empty
    if record is None:
        empty.available_audiences = available
        return empty
    return CaseStudyResponse(
        repository_id=record.repository_id,
        narrative=record.narrative,
        commit_count=record.commit_count,
        hotspot_count=record.hotspot_count,
        generated_at=record.generated_at,
        available_audiences=available,
    )


def get_patterns(
    project_root: Path, repository_id: str, hotspot_threshold: int = 10
) -> PatternReportResponse:
    """Return detected patterns with their evidence commit SHAs and time ranges."""
    from git_it.repository_ingestion.composition import build_pattern_detection_service

    db_path = db_path_for(project_root)
    if not db_path.exists():
        return _empty_patterns(repository_id)
    service = build_pattern_detection_service(project_root=project_root)
    report = service.detect(repository_id, hotspot_threshold=hotspot_threshold)
    return map_pattern_report(report)


def search_commits(
    project_root: Path,
    repository_id: str,
    category: str | None = None,
    order: str = "newest",
    limit: int = 20,
) -> CommitsResponse:
    """Search a repository's analyzed commits by category/order/limit."""
    if order not in ("newest", "oldest"):
        order = "newest"
    db_path = db_path_for(project_root)
    if not db_path.exists():
        return CommitsResponse(repository_id=repository_id, commits=[], total=0)
    reader = SqliteCommitWithAnalysisReader(db_path)
    total = reader.count_commits_with_analyses(repository_id, category=category)
    records = reader.list_commits_with_analyses(
        repository_id, limit=limit, order=order, category=category
    )
    commits = [_commit_item(r) for r in records]
    return CommitsResponse(repository_id=repository_id, commits=commits, total=total)


def get_contributors(project_root: Path, repository_id: str) -> ContributorsResponse:
    """Return per-author contribution stats; an unknown repository is empty."""
    db_path = db_path_for(project_root)
    if not db_path.exists():
        return ContributorsResponse(repository_id=repository_id, contributors=[], total=0)
    reader = SqliteContributorReader(db_path)
    records = reader.list_contributors(repository_id)
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
        repository_id=repository_id, contributors=contributors, total=len(contributors)
    )
