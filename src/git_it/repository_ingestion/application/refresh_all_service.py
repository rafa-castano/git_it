"""Refresh-all application service (spec 028, slice 1).

"Refresh all" is a batch convenience over the existing per-repository ingest flow: it
enumerates every already-ingested repository (``RepositoryListReader.list_repositories``)
and, for each, re-runs the same free commit-corpus refresh a re-pasted URL triggers today
-- ``git fetch`` on the bare cache plus commit-fact re-extraction, via
``RepositoryIngestionService.ingest`` (built per-repository by
``build_repository_ingestion_service``).

**Locked design point (spec 028, Goal 3a / non-goal):** this service must call the
per-repo ingest primitive's ``ingest`` method directly -- it must NEVER route through the
``_ingest_bg`` wrapper (``api/routes/repos.py``) or invoke any analysis/narrative/
summarizer collaborator. Those cost LLM calls; refresh-all is locked free. This module has
no dependency capable of reaching an analysis service at all -- there is no analysis port
imported here, by construction.

Per-repository failure isolation mirrors the best-effort posture already established by
``EmbeddingBackfillService`` (spec 027) and the ``_fetch_and_store_*`` helpers in
``api/routes/repos.py``: one repository's ingest raising, or returning an
``IngestionResult`` whose ``status`` is not ``"COMPLETED"``, is caught, logged by
``type(exc).__name__`` (or the ingestion result's own safe fields) only -- never a raw
exception message, which could carry a tokened fetch URL -- and marks only that repository
failed. The loop always continues with the remaining repositories.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from git_it.repository_ingestion.application.ports import (
    RepositoryListReader,
    RepositoryRecord,
)
from git_it.repository_ingestion.application.service import IngestionResult

_logger = logging.getLogger(__name__)

_COMPLETED_STATUS = "COMPLETED"


class RefreshIngestPrimitive(Protocol):
    """Structural shape RefreshAllService needs from the per-repo ingest primitive.

    ``RepositoryIngestionService`` (``application/service.py``) satisfies this Protocol
    without any changes. Kept local (rather than importing the concrete class) so this
    service depends only on the one method it calls, consistent with the hexagonal
    boundary the rest of this module keeps -- and so test doubles stay structurally typed
    without subclassing anything.
    """

    def ingest(self, raw_url: str) -> IngestionResult: ...


IngestServiceFactory = Callable[[str], RefreshIngestPrimitive]
"""Builds the per-repository ingest primitive for a given ``repository_id``.

``RepositoryIngestionService`` is built per-repository (its bare-cache path and
``repository_id`` are constructor arguments -- see ``build_repository_ingestion_service``
in ``composition.py``), so RefreshAllService is given a factory rather than one
pre-built instance, and calls it once per enumerated repository.
"""


@dataclass(frozen=True)
class RepositoryRefreshResult:
    """Per-repository outcome from one ``RefreshAllService.refresh_all()`` call."""

    repository_id: str
    canonical_url: str
    status: str  # "completed" | "failed"
    new_commits: int
    error_code: str | None = None
    safe_message: str | None = None


@dataclass(frozen=True)
class RefreshAllResult:
    """Aggregate outcome from one ``RefreshAllService.refresh_all()`` call."""

    repositories: list[RepositoryRefreshResult]
    total_repositories: int
    refreshed_count: int
    failed_count: int
    total_new_commits: int

    @property
    def nothing_to_refresh(self) -> bool:
        return self.total_repositories == 0


_EMPTY_RESULT = RefreshAllResult(
    repositories=[],
    total_repositories=0,
    refreshed_count=0,
    failed_count=0,
    total_new_commits=0,
)


class RefreshAllService:
    """Batch convenience over ``RepositoryIngestionService.ingest`` (spec 028)."""

    def __init__(
        self,
        *,
        repository_list_reader: RepositoryListReader,
        ingest_service_factory: IngestServiceFactory,
    ) -> None:
        self._repository_list_reader = repository_list_reader
        self._ingest_service_factory = ingest_service_factory

    def refresh_all(self) -> RefreshAllResult:
        """Refresh the commit corpus of every already-ingested repository.

        Sequential by design (spec 028 defers concurrency). Returns a zero-count,
        empty-list result -- with no ingest calls made -- when there are no ingested
        repositories yet.
        """
        repositories = self._repository_list_reader.list_repositories()
        if not repositories:
            return _EMPTY_RESULT

        results = [self._refresh_one(repo) for repo in repositories]

        refreshed = sum(1 for r in results if r.status == "completed")
        failed = sum(1 for r in results if r.status == "failed")
        total_new_commits = sum(r.new_commits for r in results)

        return RefreshAllResult(
            repositories=results,
            total_repositories=len(results),
            refreshed_count=refreshed,
            failed_count=failed,
            total_new_commits=total_new_commits,
        )

    def _refresh_one(self, repo: RepositoryRecord) -> RepositoryRefreshResult:
        try:
            ingest_service = self._ingest_service_factory(repo.repository_id)
            result = ingest_service.ingest(repo.canonical_url)
        except Exception as exc:  # noqa: BLE001 - one repo's failure must not abort the batch
            _logger.warning(
                "refresh failed: %s",
                type(exc).__name__,
                extra={"repository_id": repo.repository_id},
            )
            return RepositoryRefreshResult(
                repository_id=repo.repository_id,
                canonical_url=repo.canonical_url,
                status="failed",
                new_commits=0,
                error_code=None,
                safe_message=f"Refresh failed: {type(exc).__name__}",
            )

        if result.status != _COMPLETED_STATUS:
            _logger.warning(
                "refresh failed: %s",
                result.error_code or result.status,
                extra={"repository_id": repo.repository_id},
            )
            return RepositoryRefreshResult(
                repository_id=repo.repository_id,
                canonical_url=repo.canonical_url,
                status="failed",
                new_commits=0,
                error_code=result.error_code,
                safe_message=result.safe_message,
            )

        return RepositoryRefreshResult(
            repository_id=repo.repository_id,
            canonical_url=repo.canonical_url,
            status="completed",
            new_commits=result.commits_inserted or 0,
        )
