from pathlib import Path


class UnsafeWorkspaceIdentifierError(ValueError):
    pass


def ingestion_workspace_root(project_root: Path) -> Path:
    return project_root / ".data" / "git-it" / "ingestion"


def repository_cache_path(project_root: Path, *, repository_id: str) -> Path:
    _ensure_safe_identifier(repository_id)
    return ingestion_workspace_root(project_root) / "repos" / f"{repository_id}.git"


def run_artifacts_path(project_root: Path, *, ingestion_run_id: str) -> Path:
    _ensure_safe_identifier(ingestion_run_id)
    return ingestion_workspace_root(project_root) / "runs" / ingestion_run_id


def _ensure_safe_identifier(identifier: str) -> None:
    if not identifier or identifier in {".", ".."}:
        raise UnsafeWorkspaceIdentifierError(identifier)

    identifier_path = Path(identifier)
    if identifier_path.name != identifier:
        raise UnsafeWorkspaceIdentifierError(identifier)
