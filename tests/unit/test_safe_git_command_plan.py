import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from git_it.repository_ingestion.application_service import GitGatewayError
from git_it.repository_ingestion.safe_git import (
    CompletedGitProcess,
    GitCommandPlan,
    GitCommandResult,
    GitCommandTimeoutError,
    SafeGitGateway,
    SubprocessGitCommandRunner,
    plan_clone_or_fetch,
)


@dataclass(frozen=True)
class FakeCompletedProcess(CompletedGitProcess):
    returncode: int
    stderr: str | None = None


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


def test_subprocess_git_command_runner_forwards_safe_plan_without_shell() -> None:
    calls = []

    def fake_run(args: list[str], **kwargs: Any) -> FakeCompletedProcess:
        calls.append((args, kwargs))
        return FakeCompletedProcess(returncode=0)

    plan = GitCommandPlan(
        args=["git", "status"],
        env={"GIT_TERMINAL_PROMPT": "0"},
        timeout_seconds=300,
        cwd=None,
    )
    runner = SubprocessGitCommandRunner(
        run_command=fake_run,
        base_env={"PATH": "test-path", "GIT_TERMINAL_PROMPT": "1"},
    )

    result = runner.run(plan)

    assert result == GitCommandResult(exit_code=0)
    assert calls == [
        (
            ["git", "status"],
            {
                "cwd": None,
                "env": {"PATH": "test-path", "GIT_TERMINAL_PROMPT": "0"},
                "timeout": 300,
                "capture_output": True,
                "text": True,
                "check": False,
                "shell": False,
            },
        )
    ]


def test_subprocess_git_command_runner_maps_timeout_without_exposing_stderr() -> None:
    def fake_run(args: list[str], **kwargs: Any) -> FakeCompletedProcess:
        raise subprocess.TimeoutExpired(cmd=args, timeout=kwargs["timeout"], stderr="secret")

    runner = SubprocessGitCommandRunner(run_command=fake_run, base_env={})
    plan = GitCommandPlan(args=["git", "fetch"], env={}, timeout_seconds=1, cwd=None)

    with pytest.raises(GitCommandTimeoutError) as raised_error:
        runner.run(plan)

    assert "secret" not in str(raised_error.value)


def test_subprocess_git_command_runner_returns_exit_code_without_exposing_stderr() -> None:
    def fake_run(args: list[str], **kwargs: Any) -> FakeCompletedProcess:
        return FakeCompletedProcess(returncode=128, stderr="secret")

    runner = SubprocessGitCommandRunner(run_command=fake_run, base_env={})
    plan = GitCommandPlan(args=["git", "fetch"], env={}, timeout_seconds=1, cwd=None)

    result = runner.run(plan)

    assert result == GitCommandResult(exit_code=128)
