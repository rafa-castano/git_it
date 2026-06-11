from dataclasses import dataclass
from typing import Protocol

from git_it.repository_ingestion.failure_mapping import failure_for_error_code
from git_it.repository_ingestion.url_contract import (
    RepositoryUrlValidationError,
    parse_repository_url,
)


class GitGateway(Protocol):
    def clone_or_fetch(self, canonical_url: str) -> None: ...


@dataclass(frozen=True)
class IngestionResult:
    status: str
    error_code: str | None
    stage: str
    retryable: bool
    safe_message: str | None


class RepositoryIngestionService:
    def __init__(self, *, git_gateway: GitGateway) -> None:
        self._git_gateway = git_gateway

    def ingest(self, raw_url: str) -> IngestionResult:
        try:
            parse_repository_url(raw_url)
        except RepositoryUrlValidationError as error:
            failure = failure_for_error_code(error.error_code)
            return IngestionResult(
                status=failure.status,
                error_code=failure.error_code,
                stage=failure.stage,
                retryable=failure.retryable,
                safe_message=error.safe_message,
            )

        raise NotImplementedError("valid repository ingestion is not implemented yet")
