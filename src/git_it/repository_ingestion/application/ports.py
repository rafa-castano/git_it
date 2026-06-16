from dataclasses import dataclass
from typing import Protocol

from git_it.repository_ingestion.domain.analysis import CommitAnalysis
from git_it.repository_ingestion.domain.commits import ExtractedCommit

__all__ = [
    "CommitAnalysis",
    "CommitAnalysisClient",
    "CommitExtractor",
    "CommitFactWriter",
    "CommitPersistenceResult",
    "ExtractedCommit",
    "FileFactWriter",
    "GitGateway",
    "GitGatewayError",
    "IngestionRunRecord",
    "IngestionRunWriter",
    "LLMClient",
    "LLMMessage",
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


@dataclass(frozen=True)
class CommitPersistenceResult:
    inserted: int
    reused: int


class CommitFactWriter(Protocol):
    def save_commit_facts(
        self,
        commits: list[ExtractedCommit],
        *,
        repository_id: str,
    ) -> CommitPersistenceResult: ...


class FileFactWriter(Protocol):
    def save_file_facts(
        self,
        commits: list[ExtractedCommit],
        *,
        repository_id: str,
    ) -> CommitPersistenceResult: ...


class GitGatewayError(Exception):
    safe_message = "Repository fetch failed safely before analysis could start."

    def __init__(self, *, error_code: str) -> None:
        super().__init__(self.safe_message)
        self.error_code = error_code


class CommitExtractor(Protocol):
    def extract_commits(self) -> list[ExtractedCommit]: ...


class GitGateway(Protocol):
    def clone_or_fetch(self, canonical_url: str) -> None: ...


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str


class LLMClient(Protocol):
    def complete(self, messages: list[LLMMessage]) -> str: ...


class CommitAnalysisClient(Protocol):
    def analyze_commit(self, messages: list[LLMMessage]) -> CommitAnalysis: ...
