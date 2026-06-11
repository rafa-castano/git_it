from pathlib import Path

import pytest

from git_it.repository_ingestion.application_service import GitGatewayError
from git_it.repository_ingestion.safe_git import (
    GitCommandPlan,
    GitCommandResult,
    GitCommandTimeoutError,
    SafeGitGateway,
    plan_clone_or_fetch,
)


def test_safe_git_plan_uses_bare_clone_without_checkout_submodules_or_lfs(tmp_path: Path) -> None:
    cache_path = tmp_path / "repo-cache.git"

    plan = plan_clone_or_fetch(
        canonical_url="https://github.com/owner/repo",
        cache_path=cache_path,
    )

    assert plan.timeout_seconds == 300
    assert plan.cwd is None
    assert plan.env["GIT_TERMINAL_PROMPT"] == "0"
    assert plan.env["GIT_LFS_SKIP_SMUDGE"] == "1"
    assert plan.args == [
        "git",
        "-c",
        "protocol.file.allow=never",
        "clone",
        "--bare",
        "--no-checkout",
        "--no-recurse-submodules",
        "https://github.com/owner/repo",
        str(cache_path),
    ]


def test_safe_git_plan_fetches_existing_bare_cache_without_submodules_or_lfs(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "repo-cache.git"
    cache_path.mkdir()

    plan = plan_clone_or_fetch(
        canonical_url="https://github.com/owner/repo",
        cache_path=cache_path,
    )

    assert plan.timeout_seconds == 300
    assert plan.cwd is None
    assert plan.env["GIT_TERMINAL_PROMPT"] == "0"
    assert plan.env["GIT_LFS_SKIP_SMUDGE"] == "1"
    assert plan.args == [
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


class RecordingGitCommandRunner:
    def __init__(self, *, exit_code: int = 0) -> None:
        self.exit_code = exit_code
        self.plans: list[GitCommandPlan] = []

    def run(self, plan: GitCommandPlan) -> GitCommandResult:
        self.plans.append(plan)
        return GitCommandResult(exit_code=self.exit_code)


class TimeoutGitCommandRunner:
    def run(self, plan: GitCommandPlan) -> GitCommandResult:
        raise GitCommandTimeoutError


def test_safe_git_gateway_runs_planned_command_through_injected_runner(tmp_path: Path) -> None:
    cache_path = tmp_path / "repo-cache.git"
    runner = RecordingGitCommandRunner()
    gateway = SafeGitGateway(cache_path=cache_path, runner=runner)

    gateway.clone_or_fetch("https://github.com/owner/repo")

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
        str(cache_path),
    ]


def test_safe_git_gateway_maps_runner_timeout_to_clone_timeout(tmp_path: Path) -> None:
    gateway = SafeGitGateway(
        cache_path=tmp_path / "repo-cache.git",
        runner=TimeoutGitCommandRunner(),
    )

    with pytest.raises(GitGatewayError) as raised_error:
        gateway.clone_or_fetch("https://github.com/owner/repo")

    assert raised_error.value.error_code == "CLONE_TIMEOUT"
    assert str(raised_error.value) == "Repository fetch failed safely before analysis could start."


def test_safe_git_gateway_maps_non_zero_exit_to_git_fetch_failed(tmp_path: Path) -> None:
    gateway = SafeGitGateway(
        cache_path=tmp_path / "repo-cache.git",
        runner=RecordingGitCommandRunner(exit_code=128),
    )

    with pytest.raises(GitGatewayError) as raised_error:
        gateway.clone_or_fetch("https://github.com/owner/repo")

    assert raised_error.value.error_code == "GIT_FETCH_FAILED"
    assert str(raised_error.value) == "Repository fetch failed safely before analysis could start."
