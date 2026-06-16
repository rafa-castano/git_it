from dataclasses import dataclass
from typing import Protocol

from git_it.repository_ingestion.domain.analysis import CommitAnalysis
from git_it.repository_ingestion.domain.commits import ExtractedCommit

__all__ = [
    "CaseStudyRecord",
    "CaseStudyStore",
    "CommitAnalysis",
    "CommitAnalysisClient",
    "CommitAnalysisReader",
    "CommitAnalysisWriter",
    "CommitExtractor",
    "CommitFactWriter",
    "CommitPersistenceResult",
    "CommitSummaryReader",
    "CommitSummaryRecord",
    "ExtractedCommit",
    "FileChurnRecord",
    "FileFactReader",
    "FileFactWriter",
    "FileOwnershipRecord",
    "GitGateway",
    "GitGatewayError",
    "IngestionRunRecord",
    "IngestionRunWriter",
    "LLMClient",
    "LLMMessage",
    "OwnershipReader",
    "TemporalAnalysisReader",
    "TimestampedAnalysis",
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


@dataclass(frozen=True)
class FileChurnRecord:
    file_path: str
    commit_count: int
    total_insertions: int
    total_deletions: int


class FileFactReader(Protocol):
    def get_file_churn(self, repository_id: str) -> list[FileChurnRecord]: ...


@dataclass(frozen=True)
class FileOwnershipRecord:
    file_path: str
    author_count: int
    commit_count: int


class OwnershipReader(Protocol):
    def get_file_ownership(self, repository_id: str) -> list[FileOwnershipRecord]: ...


@dataclass(frozen=True)
class CommitSummaryRecord:
    sha: str
    message: str


class CommitSummaryReader(Protocol):
    def list_commit_messages(self, repository_id: str) -> list[CommitSummaryRecord]: ...


@dataclass(frozen=True)
class CaseStudyRecord:
    repository_id: str
    narrative: str
    commit_count: int
    hotspot_count: int


class CaseStudyStore(Protocol):
    def save_case_study(self, record: CaseStudyRecord) -> None: ...

    def get_case_study(self, repository_id: str) -> CaseStudyRecord | None: ...


class CommitAnalysisWriter(Protocol):
    def save_analysis(self, analysis: CommitAnalysis, *, repository_id: str) -> bool: ...


class CommitAnalysisReader(Protocol):
    def get_analysis(self, *, repository_id: str, commit_sha: str) -> CommitAnalysis | None: ...

    def list_analyses(
        self, repository_id: str, *, limit: int | None = None
    ) -> list[CommitAnalysis]: ...


@dataclass(frozen=True)
class TimestampedAnalysis:
    analysis: CommitAnalysis
    committed_at: str


class TemporalAnalysisReader(Protocol):
    def list_analyses_with_dates(self, repository_id: str) -> list[TimestampedAnalysis]: ...
