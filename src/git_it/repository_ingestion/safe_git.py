from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitCommandPlan:
    args: list[str]
    env: dict[str, str]
    timeout_seconds: int
    cwd: Path | None


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
