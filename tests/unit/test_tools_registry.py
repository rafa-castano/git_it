"""Spec 012 AC-1 — shared tool layer extracted from the MCP server.

The five tool implementations live as plain functions in `git_it.tools.registry`,
callable directly (by the chat service) and wrapped by the MCP server. These tests
exercise the functions directly — no MCP transport — and reuse the DB seeding
helpers from the MCP tool tests.
"""

from pathlib import Path

from git_it.api.schemas import (
    CaseStudyResponse,
    CommitsResponse,
    ContributorsResponse,
    PatternReportResponse,
    RepoListResponse,
)
from git_it.repository_ingestion.application.ports import (
    CaseStudyRecord,
    CommitWithAnalysisRecord,
    ContributorRecord,
    RepositoryRecord,
)
from git_it.repository_ingestion.domain.patterns import CategoryCount, PatternReport
from tests.unit.test_mcp_tools import (
    _db_path,
    _init_db,
    _insert_analysis,
    _insert_case_study,
    _insert_commit,
    _insert_file_fact,
    _insert_ingestion_run,
)


def test_list_repositories_returns_model(tmp_path: Path) -> None:
    from git_it.tools import registry

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(
        db, repository_id="repo-abc", canonical_url="https://github.com/test/repo"
    )
    _insert_commit(db, repository_id="repo-abc", sha="aaa111")

    result = registry.list_repositories(tmp_path)
    assert isinstance(result, RepoListResponse)
    assert result.total == 1
    assert result.repos[0].repository_id == "repo-abc"


def test_get_case_study_returns_model_with_audiences(tmp_path: Path) -> None:
    from git_it.tools import registry

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_case_study(db, repository_id="repo-cs", audience="beginner", narrative="Fascinating.")

    result = registry.get_case_study(tmp_path, "repo-cs", "beginner")
    assert isinstance(result, CaseStudyResponse)
    assert "Fascinating" in result.narrative
    assert "beginner" in result.available_audiences


def test_search_commits_filters_by_category(tmp_path: Path) -> None:
    from git_it.tools import registry

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db, repository_id="repo-abc")
    _insert_commit(db, sha="feat001")
    _insert_analysis(db, commit_sha="feat001", category="feature")
    _insert_commit(db, sha="fix001", committed_at="2024-02-01T10:00:00")
    _insert_analysis(db, commit_sha="fix001", category="bugfix")

    result = registry.search_commits(tmp_path, "repo-abc", category="feature")
    assert isinstance(result, CommitsResponse)
    assert result.total == 1
    assert result.commits[0].category == "feature"


def test_get_patterns_returns_evidence(tmp_path: Path) -> None:
    from git_it.tools import registry

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db, repository_id="repo-abc")
    for i in range(10):
        sha = f"sha{i:04d}"
        _insert_commit(db, sha=sha, committed_at=f"2024-01-{i + 1:02d}T10:00:00")
        _insert_file_fact(db, commit_sha=sha, file_path="src/hotfile.py")

    result = registry.get_patterns(tmp_path, "repo-abc", hotspot_threshold=5)
    assert isinstance(result, PatternReportResponse)
    assert result.hotspots[0].file_path == "src/hotfile.py"
    assert len(result.hotspots[0].evidence_commit_shas) >= 1


def test_get_contributors_unknown_repo_is_empty(tmp_path: Path) -> None:
    from git_it.tools import registry

    db = _db_path(tmp_path)
    _init_db(db)

    result = registry.get_contributors(tmp_path, "repo-missing")
    assert isinstance(result, ContributorsResponse)
    assert result.contributors == []
    assert result.total == 0


def test_registry_delegates_reads_to_backend_aware_builders(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from git_it.tools import registry

    calls: list[str] = []

    monkeypatch.setattr(
        registry,
        "database_is_provisioned",
        lambda *, project_root: True,
    )

    class RepoReader:
        def list_repositories(self) -> list[RepositoryRecord]:
            calls.append("repositories")
            return [
                RepositoryRecord(
                    repository_id="repo-1",
                    canonical_url="https://github.com/acme/repo",
                    status="COMPLETED",
                    commit_count=1,
                    analysis_count=1,
                    has_case_study=True,
                )
            ]

    class CaseStudyStore:
        def get_case_study(
            self, repository_id: str, audience: str = "beginner"
        ) -> CaseStudyRecord | None:
            calls.append("case-study")
            return CaseStudyRecord(
                repository_id=repository_id,
                narrative="Narrative",
                commit_count=1,
                hotspot_count=0,
                audience=audience,
            )

        def list_available_audiences(self, repository_id: str) -> list[str]:
            return ["beginner"]

    class CommitReader:
        def count_commits_with_analyses(self, repository_id: str, *, category: str | None) -> int:
            calls.append("commit-count")
            return 1

        def list_commits_with_analyses(
            self,
            repository_id: str,
            *,
            limit: int,
            order: str = "newest",
            category: str | None = None,
        ) -> list[CommitWithAnalysisRecord]:
            calls.append("commits")
            return [
                CommitWithAnalysisRecord(
                    sha="abc123",
                    message="feat: test",
                    committed_at="2024-01-01T00:00:00",
                    analysis_data='{"category": "feature", "risk_level": "low"}',
                )
            ]

    class ContributorReader:
        def list_contributors(self, repository_id: str) -> list[ContributorRecord]:
            calls.append("contributors")
            return [
                ContributorRecord(
                    author_name="Alice",
                    commit_count=1,
                    first_commit="2024-01-01T00:00:00",
                    last_commit="2024-01-01T00:00:00",
                    is_bot=False,
                    active_days=1,
                    github_username=None,
                    category_counts={"feature": 1},
                    top_files=["src/app.py"],
                )
            ]

    class PatternService:
        def detect(self, repository_id: str, *, hotspot_threshold: int = 10) -> PatternReport:
            calls.append("patterns")
            return PatternReport(
                repository_id=repository_id,
                hotspots=[],
                category_counts=[CategoryCount(category="feature", count=1)],
            )

    monkeypatch.setattr(
        registry, "build_repository_list_reader", lambda *, project_root: RepoReader()
    )
    monkeypatch.setattr(
        registry, "build_case_study_store", lambda *, project_root: CaseStudyStore()
    )
    monkeypatch.setattr(
        registry, "build_commit_with_analysis_reader", lambda *, project_root: CommitReader()
    )
    monkeypatch.setattr(
        registry, "build_contributor_reader", lambda *, project_root: ContributorReader()
    )
    monkeypatch.setattr(
        registry, "build_pattern_detection_service", lambda *, project_root: PatternService()
    )

    assert registry.list_repositories(tmp_path).total == 1
    assert registry.get_case_study(tmp_path, "repo-1").narrative == "Narrative"
    assert registry.search_commits(tmp_path, "repo-1").total == 1
    assert registry.get_contributors(tmp_path, "repo-1").total == 1
    assert registry.get_patterns(tmp_path, "repo-1").category_counts[0].category == "feature"

    assert calls == [
        "repositories",
        "case-study",
        "commit-count",
        "commits",
        "contributors",
        "patterns",
    ]
