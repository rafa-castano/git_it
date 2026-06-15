from pathlib import Path

import pytest

from git_it.repository_ingestion.infrastructure.workspace import (
    UnsafeWorkspaceIdentifierError,
    ingestion_workspace_root,
    repository_cache_path,
    run_artifacts_path,
)


def test_builds_ingestion_workspace_root_under_project_data_directory() -> None:
    project_root = Path("/workspace/git-it")

    path = ingestion_workspace_root(project_root)

    assert path == project_root / ".data" / "git-it" / "ingestion"


def test_builds_repository_cache_path_from_generated_repository_id() -> None:
    project_root = Path("/workspace/git-it")

    path = repository_cache_path(project_root, repository_id="repo_123")

    assert path == project_root / ".data" / "git-it" / "ingestion" / "repos" / "repo_123.git"
    assert path.is_relative_to(project_root)


def test_builds_run_artifacts_path_from_generated_ingestion_run_id() -> None:
    project_root = Path("/workspace/git-it")

    path = run_artifacts_path(project_root, ingestion_run_id="run_456")

    assert path == project_root / ".data" / "git-it" / "ingestion" / "runs" / "run_456"
    assert path.is_relative_to(project_root)


@pytest.mark.parametrize(
    "unsafe_identifier",
    [
        "../outside",
        "owner/repo",
        "branch/name",
        "",
        ".",
        "..",
    ],
)
def test_rejects_identifiers_that_could_escape_or_encode_external_names(
    unsafe_identifier: str,
) -> None:
    project_root = Path("/workspace/git-it")

    with pytest.raises(UnsafeWorkspaceIdentifierError):
        repository_cache_path(project_root, repository_id=unsafe_identifier)

    with pytest.raises(UnsafeWorkspaceIdentifierError):
        run_artifacts_path(project_root, ingestion_run_id=unsafe_identifier)
