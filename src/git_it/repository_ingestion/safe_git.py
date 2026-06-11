from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from git_it.repository_ingestion.application_service import GitGatewayError


@dataclass(frozen=True)
class GitCommandPlan:
    args: list[str]
    env: dict[str, str]
    timeout_seconds: int
    cwd: Path | None


@dataclass(frozen=True)
class GitCommandResult:
    exit_code: int


class GitCommandTimeoutError(TimeoutError):
    pass


class GitCommandRunner(Protocol):
    def run(self, plan: GitCommandPlan) -> GitCommandResult: ...


class SafeGitGateway:
    def __init__(self, *, cache_path: Path, runner: GitCommandRunner) -> None:
        self._cache_path = cache_path
        self._runner = runner

    def clone_or_fetch(self, canonical_url: str) -> None:
        plan = plan_clone_or_fetch(
            canonical_url=canonical_url,
            cache_path=self._cache_path,
        )

        try:
            result = self._runner.run(plan)
        except GitCommandTimeoutError as error:
            raise GitGatewayError(error_code="CLONE_TIMEOUT") from error

        if result.exit_code != 0:
            raise GitGatewayError(error_code="GIT_FETCH_FAILED")


def plan_clone_or_fetch(
    *,
    canonical_url: str,
    cache_path: Path,
    timeout_seconds: int = 300,
) -> GitCommandPlan:
    env = {
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_LFS_SKIP_SMUDGE": "1",
    }

    if cache_path.exists():
        return GitCommandPlan(
            args=[
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
            ],
            env=env,
            timeout_seconds=timeout_seconds,
            cwd=None,
        )

    return GitCommandPlan(
        args=[
            "git",
            "-c",
            "protocol.file.allow=never",
            "clone",
            "--bare",
            "--no-checkout",
            "--no-recurse-submodules",
            canonical_url,
            str(cache_path),
        ],
        env=env,
        timeout_seconds=timeout_seconds,
        cwd=None,
    )
