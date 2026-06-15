from pathlib import Path

from git_it.repository_ingestion.composition import build_repository_ingestion_service
from git_it.repository_ingestion.infrastructure.git import GitCommandPlan, GitCommandResult


class RecordingGitCommandRunner:
    def __init__(self) -> None:
        self.plans: list[GitCommandPlan] = []

    def run(self, plan: GitCommandPlan) -> GitCommandResult:
        self.plans.append(plan)
        return GitCommandResult(exit_code=0)


def test_build_repository_ingestion_service_wires_safe_git_gateway_to_workspace_cache(
    tmp_path: Path,
) -> None:
    runner = RecordingGitCommandRunner()
    service = build_repository_ingestion_service(
        project_root=tmp_path,
        repository_id="repo-123",
        runner=runner,
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
