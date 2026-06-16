from dataclasses import dataclass
from typing import Protocol

from git_it.repository_ingestion.domain.commits import ExtractedCommit

__all__ = [
    "CommitExtractor",
    "ExtractedCommit",
    "GitGateway",
    "GitGatewayError",
    "IngestionRunRecord",
    "IngestionRunWriter",
]


@dataclass(frozen=True)
class IngestionRunRecord:
    run_id: str
    repository_id: str
    canonical_url: str
    status: str
    started_at: str
    completed_at: str | None
    error_code: str | None
    error_stage: str | None
    retryable: bool | None
    safe_message: str | None


class IngestionRunWriter(Protocol):
    def save_ingestion_run(self, record: IngestionRunRecord) -> None: ...


class GitGatewayError(Exception):
    safe_message = "Repository fetch failed safely before analysis could start."

    def __init__(self, *, error_code: str) -> None:
        super().__init__(self.safe_message)
        self.error_code = error_code


class CommitExtractor(Protocol):
    def extract_commits(self) -> list[ExtractedCommit]: ...


class GitGateway(Protocol):
    def clone_or_fetch(self, canonical_url: str) -> None: ...
