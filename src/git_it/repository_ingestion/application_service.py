from dataclasses import dataclass
from typing import Protocol

from git_it.repository_ingestion.failure_mapping import failure_for_error_code
from git_it.repository_ingestion.url_contract import (
    RepositoryUrlValidationError,
    parse_repository_url,
)


class GitGatewayError(Exception):
    safe_message = "Repository fetch failed safely before analysis could start."

    def __init__(self, *, error_code: str) -> None:
        super().__init__(self.safe_message)
        self.error_code = error_code


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
            parsed_url = parse_repository_url(raw_url)
        except RepositoryUrlValidationError as error:
            failure = failure_for_error_code(error.error_code)
            return IngestionResult(
                status=failure.status,
                error_code=failure.error_code,
                stage=failure.stage,
                retryable=failure.retryable,
                safe_message=error.safe_message,
            )

        try:
            self._git_gateway.clone_or_fetch(parsed_url.canonical_url)
        except GitGatewayError as error:
            failure = failure_for_error_code(error.error_code)
            return IngestionResult(
                status=failure.status,
                error_code=failure.error_code,
                stage=failure.stage,
                retryable=failure.retryable,
                safe_message=error.safe_message,
            )

        return IngestionResult(
            status="CLONING_OR_FETCHING",
            error_code=None,
            stage="CLONING_OR_FETCHING",
            retryable=False,
            safe_message=None,
        )
