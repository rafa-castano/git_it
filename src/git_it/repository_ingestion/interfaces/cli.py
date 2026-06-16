import argparse
import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from git_it.repository_ingestion.application.commit_query_service import (
    CommitRecord,
    RepositoryCommitQueryService,
)
from git_it.repository_ingestion.application.service import IngestionResult
from git_it.repository_ingestion.composition import (
    build_repository_commit_query_service,
    build_repository_ingestion_service,
)
from git_it.repository_ingestion.domain.url_contract import parse_repository_url


class IngestionService(Protocol):
    def ingest(self, raw_url: str) -> IngestionResult: ...


class ServiceFactory(Protocol):
    def __call__(self, *, project_root: Path, repository_id: str) -> IngestionService: ...


class CommitQueryService(Protocol):
    def list_commits(
        self,
        repository_id: str,
        *,
        limit: int | None = None,
    ) -> list[CommitRecord]: ...


class CommitQueryFactory(Protocol):
    def __call__(self, *, project_root: Path, repository_id: str) -> CommitQueryService: ...


_FAILED_STATUSES = {
    "FAILED_VALIDATION",
    "FAILED_FETCH",
    "FAILED_EXTRACTION",
    "FAILED_PERSISTENCE",
    "LIMIT_EXCEEDED",
    "CANCELLED",
}

_DEFAULT_COMMITS_LIMIT = 20


def repository_id_for_url(raw_url: str) -> str:
    try:
        canonical_url = parse_repository_url(raw_url).canonical_url
    except ValueError:
        canonical_url = raw_url
    digest = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:16]
    return f"repo-{digest}"


def _default_commit_query_factory(
    *, project_root: Path, repository_id: str
) -> RepositoryCommitQueryService:
    return build_repository_commit_query_service(project_root=project_root)


def main(
    argv: Sequence[str] | None = None,
    *,
    project_root: Path | None = None,
    service_factory: ServiceFactory = build_repository_ingestion_service,
    commit_query_factory: CommitQueryFactory = _default_commit_query_factory,
) -> int:
    parser = argparse.ArgumentParser(prog="git-it")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("repository_url")

    commits_parser = subparsers.add_parser("commits")
    commits_parser.add_argument("repository_url")
    commits_parser.add_argument("--limit", type=int, default=_DEFAULT_COMMITS_LIMIT)

    args = parser.parse_args(argv)
    resolved_root = Path.cwd() if project_root is None else project_root

    if args.command == "ingest":
        return _run_ingest(
            raw_url=args.repository_url,
            project_root=resolved_root,
            service_factory=service_factory,
        )

    if args.command == "commits":
        return _run_commits(
            raw_url=args.repository_url,
            limit=args.limit,
            project_root=resolved_root,
            commit_query_factory=commit_query_factory,
        )

    parser.error(f"unsupported command: {args.command}")


def _run_ingest(
    *,
    raw_url: str,
    project_root: Path,
    service_factory: ServiceFactory,
) -> int:
    service = service_factory(
        project_root=project_root,
        repository_id=repository_id_for_url(raw_url),
    )
    result = service.ingest(raw_url)
    _print_ingestion_result(result)
    return 1 if result.status in _FAILED_STATUSES else 0


def _run_commits(
    *,
    raw_url: str,
    limit: int,
    project_root: Path,
    commit_query_factory: CommitQueryFactory,
) -> int:
    repository_id = repository_id_for_url(raw_url)
    service = commit_query_factory(project_root=project_root, repository_id=repository_id)
    commits = service.list_commits(repository_id, limit=limit)
    _print_commits(commits)
    return 0


def _print_commits(commits: list[CommitRecord]) -> None:
    if not commits:
        print("No commits stored for this repository. Run 'git-it ingest <url>' first.")
        return
    for commit in commits:
        sha_short = commit.sha[:7]
        date = commit.committed_at[:10]
        message = commit.message.splitlines()[0][:72]
        print(f"{sha_short}  {date}  {message}  ({commit.author_name})")


def _print_ingestion_result(result: IngestionResult) -> None:
    if result.status in _FAILED_STATUSES:
        print(f"Ingestion failed: {result.error_code}")
        if result.run_id is not None:
            print(f"Run ID: {result.run_id}")
        if result.safe_message is not None:
            print(result.safe_message)
        return

    print(f"Ingestion status: {result.status}")
    if result.canonical_url is not None:
        owner_repo = result.canonical_url.removeprefix("https://github.com/")
        print(f"Repository: {owner_repo}")
        print(f"Canonical URL: {result.canonical_url}")
    if result.commits_inserted is not None and result.commits_reused is not None:
        print(f"Commits: {result.commits_inserted} inserted, {result.commits_reused} reused")
    if result.files_inserted is not None and result.files_reused is not None:
        print(f"Files: {result.files_inserted} inserted, {result.files_reused} reused")
    if result.run_id is not None:
        print(f"Run ID: {result.run_id}")
