from pathlib import Path

import git

from git_it.repository_ingestion.application.ports import ExtractedCommit
from git_it.repository_ingestion.composition import build_repository_ingestion_service
from git_it.repository_ingestion.infrastructure.git import GitCommandPlan, GitCommandResult
from git_it.repository_ingestion.infrastructure.sqlite import SqliteIngestionRunStore
from git_it.repository_ingestion.infrastructure.workspace import ingestion_workspace_root


class RecordingGitCommandRunner:
    def __init__(self) -> None:
        self.plans: list[GitCommandPlan] = []

    def run(self, plan: GitCommandPlan) -> GitCommandResult:
        self.plans.append(plan)
        return GitCommandResult(exit_code=0)


class NullCommitExtractor:
    def extract_commits(self) -> list[ExtractedCommit]:
        return []


def test_build_repository_ingestion_service_wires_safe_git_gateway_to_workspace_cache(
    tmp_path: Path,
) -> None:
    runner = RecordingGitCommandRunner()
    service = build_repository_ingestion_service(
        project_root=tmp_path,
        repository_id="repo-123",
        runner=runner,
        commit_extractor=NullCommitExtractor(),
    )

    result = service.ingest("https://github.com/owner/repo.git")

    assert result.status == "CLONING_OR_FETCHING"
    assert len(runner.plans) == 1
    assert runner.plans[0].args == [
        "git",
        "-c",
        "protocol.file.allow=never",
        "clone",
        "--bare",
        "--no-checkout",
        "--no-recurse-submodules",
        "https://github.com/owner/repo",
        str(tmp_path / ".data" / "git-it" / "ingestion" / "repos" / "repo-123.git"),
    ]


def test_build_repository_ingestion_service_reuses_existing_bare_cache(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / ".data" / "git-it" / "ingestion" / "repos" / "repo-123.git"
    cache_path.mkdir(parents=True)
    runner = RecordingGitCommandRunner()
    service = build_repository_ingestion_service(
        project_root=tmp_path,
        repository_id="repo-123",
        runner=runner,
        commit_extractor=NullCommitExtractor(),
    )

    result = service.ingest("https://github.com/owner/repo")

    assert result.status == "CLONING_OR_FETCHING"
    assert len(runner.plans) == 1
    assert runner.plans[0].args == [
        "git",
        "--git-dir",
        str(cache_path),
        "-c",
        "protocol.file.allow=never",
        "fetch",
        "--prune",
        "--tags",
        "--no-recurse-submodules",
        "origin",
        "+refs/heads/*:refs/heads/*",
        "+refs/tags/*:refs/tags/*",
    ]


def test_build_repository_ingestion_service_wires_default_sqlite_run_store(
    tmp_path: Path,
) -> None:
    runner = RecordingGitCommandRunner()
    service = build_repository_ingestion_service(
        project_root=tmp_path,
        repository_id="repo-123",
        runner=runner,
        commit_extractor=NullCommitExtractor(),
    )

    result = service.ingest("https://github.com/owner/repo")

    store = SqliteIngestionRunStore(ingestion_workspace_root(tmp_path) / "git-it.sqlite3")
    runs = store.list_ingestion_runs_for_repository("repo-123")
    assert result.run_id is not None
    assert len(runs) == 1
    assert runs[0].run_id == result.run_id
    assert runs[0].repository_id == "repo-123"
    assert runs[0].canonical_url == "https://github.com/owner/repo"
    assert runs[0].status == "CLONING_OR_FETCHING"


def test_build_repository_ingestion_service_wires_gitpython_extractor_by_default(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source_repo = git.Repo.init(str(source))
    with source_repo.config_writer() as cfg:
        cfg.set_value("user", "name", "Test Author")
        cfg.set_value("user", "email", "test@example.com")
    (source / "README.md").write_text("hello")
    source_repo.index.add(["README.md"])
    source_repo.index.commit("initial commit")
    (source / "b.txt").write_text("second")
    source_repo.index.add(["b.txt"])
    source_repo.index.commit("second commit")

    cache_path = tmp_path / ".data" / "git-it" / "ingestion" / "repos" / "repo-123.git"
    source_repo.clone(str(cache_path), bare=True)

    runner = RecordingGitCommandRunner()
    service = build_repository_ingestion_service(
        project_root=tmp_path,
        repository_id="repo-123",
        runner=runner,
    )

    result = service.ingest("https://github.com/owner/repo")

    assert result.commits_inserted == 2
    assert result.commits_reused == 0
