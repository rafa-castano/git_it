from pathlib import Path

from git_it.repository_ingestion.safe_git import plan_clone_or_fetch


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
