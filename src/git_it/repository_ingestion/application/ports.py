from dataclasses import dataclass
from typing import Protocol

from git_it.repository_ingestion.domain.advisories import AdvisoryEvidence
from git_it.repository_ingestion.domain.analysis import CommitAnalysis
from git_it.repository_ingestion.domain.commits import ExtractedCommit
from git_it.repository_ingestion.domain.discussions import DiscussionEvidence
from git_it.repository_ingestion.domain.embeddings import EmbeddedChunk
from git_it.repository_ingestion.domain.github_context import GithubContext
from git_it.repository_ingestion.domain.patterns import PatternExplanation, PatternReport
from git_it.repository_ingestion.domain.project_docs import ProjectDocContent
from git_it.repository_ingestion.domain.releases import ReleaseEvidence

DEFAULT_AUDIENCE = "beginner"  # canonical audience default used across all layers

__all__ = [
    "AdvisoryEvidence",
    "AdvisoryEvidenceReader",
    "CaseStudyRecord",
    "CaseStudyStore",
    "CommitAnalysis",
    "CommitAnalysisClient",
    "CommitAnalysisReader",
    "CommitAnalysisWriter",
    "CommitCountReader",
    "CommitDateReader",
    "CommitExtractor",
    "CommitFactWriter",
    "CommitPersistenceResult",
    "CommitSummaryReader",
    "CommitSummaryRecord",
    "CommitWithAnalysisReader",
    "CommitWithAnalysisRecord",
    "ContributorReader",
    "ContributorRecord",
    "DEFAULT_AUDIENCE",
    "DefaultBranchReader",
    "DefaultBranchWriter",
    "DiscussionEvidence",
    "DiscussionEvidenceReader",
    "EmbeddingAnalyzer",
    "EmbeddingClient",
    "EmbeddingReader",
    "EmbeddingWriter",
    "ExtractedCommit",
    "FileChurnRecord",
    "FileEvidenceReader",
    "FileFactReader",
    "FileFactWriter",
    "FileOwnershipRecord",
    "GitGateway",
    "GitGatewayError",
    "GithubContext",
    "GithubContextReader",
    "IngestionRunRecord",
    "IngestionRunWriter",
    "LLMClient",
    "LLMMessage",
    "OwnershipReader",
    "PatternSynthesisClient",
    "ProjectDocContent",
    "ProjectDocReader",
    "ProjectDocWriter",
    "ReleaseEvidence",
    "ReleaseEvidenceReader",
    "RepoContextReader",
    "RepositoryListReader",
    "RepositoryRecord",
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


class DefaultBranchReader(Protocol):
    """Reads a repository's default branch from its local clone (spec 020).

    Token-independent — implementations must never make a GitHub API call.
    Every failure mode (detached HEAD, unresolvable/unsafe ref, missing
    clone) degrades to ``None`` rather than raising.
    """

    def read_default_branch(self) -> str | None: ...


class DefaultBranchWriter(Protocol):
    def save_default_branch(self, repository_id: str, default_branch: str) -> None: ...


class ProjectDocReader(Protocol):
    """Reads a repository's captured README/CHANGELOG excerpt (spec 025).

    Implementations must never make a GitHub API call — this reads only from
    the local git clone already required for commit mining.
    """

    def get_project_docs(self, repository_id: str) -> ProjectDocContent | None: ...


class ProjectDocWriter(Protocol):
    def save_project_docs(self, content: ProjectDocContent) -> None: ...


class DiscussionEvidenceReader(Protocol):
    """Reads stored, schema-validated discussion evidence for a repository (spec 022).

    Returns the full currently-stored set — there is no incremental "new since last
    generation" filtering for discussion evidence (see spec 022 Non-goals); the set is
    already bounded to at most 20 short summaries per repository.
    """

    def get_discussion_evidence(self, repository_id: str) -> list[DiscussionEvidence]: ...


class ReleaseEvidenceReader(Protocol):
    """Reads stored, schema-validated release evidence for a repository (spec 026).

    Returns the full currently-stored set — mirrors ``DiscussionEvidenceReader``'s
    scope (no incremental "new since last generation" filtering).
    """

    def get_release_evidence(self, repository_id: str) -> list[ReleaseEvidence]: ...


class AdvisoryEvidenceReader(Protocol):
    """Reads stored, schema-validated security-advisory evidence for a repository
    (spec 026).

    Returns the full currently-stored set — mirrors ``DiscussionEvidenceReader``'s
    scope (no incremental "new since last generation" filtering).
    """

    def get_advisory_evidence(self, repository_id: str) -> list[AdvisoryEvidence]: ...


class EmbeddingClient(Protocol):
    """Computes an embedding vector for already-validated summary text (spec 023).

    Mirrors ``LLMClient``'s minimalism — a single method, no batching, no model
    selection at the call site (the model is fixed at construction time).
    """

    def embed(self, text: str) -> list[float]: ...


class EmbeddingReader(Protocol):
    """Reads every persisted embedding vector for a repository (spec 023).

    Backing stores (``SqliteEmbeddingStore``/``PostgresEmbeddingStore``) already
    implement this shape structurally; this Protocol formalizes it as the port
    ``SemanticSearchService`` depends on.
    """

    def get_all_embeddings(self, repository_id: str) -> list[EmbeddedChunk]: ...


class EmbeddingWriter(Protocol):
    """Persists computed embedding vectors for a repository (spec 023).

    Backing stores (``SqliteEmbeddingStore``/``PostgresEmbeddingStore``) already
    implement this shape structurally; this Protocol formalizes it as the port
    ``CommitAnalysisService`` (and the discussion-evidence ingest flow) depend on,
    so callers don't need to import concrete infrastructure classes.
    """

    def save_embeddings(self, repository_id: str, items: list[EmbeddedChunk]) -> None: ...


class EmbeddingAnalyzer(Protocol):
    """Computes an embedding for a freshly-produced ``CommitAnalysis`` (spec 023).

    ``EmbeddingService`` implements this shape structurally; this Protocol formalizes
    it as the port ``CommitAnalysisService`` depends on, so it does not need to import
    the concrete application-layer ``EmbeddingService`` class, and test doubles stay
    structurally typed without subclassing it.
    """

    def embed_commit_analysis(
        self, repository_id: str, analysis: CommitAnalysis
    ) -> EmbeddedChunk | None: ...


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str


class LLMClient(Protocol):
    def complete(self, messages: list[LLMMessage]) -> str: ...


class CommitAnalysisClient(Protocol):
    def analyze_commit(self, system: str, messages: list[LLMMessage]) -> CommitAnalysis: ...


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
    generated_at: str | None = None
    audience: str = DEFAULT_AUDIENCE


class CaseStudyStore(Protocol):
    def save_case_study(self, record: CaseStudyRecord) -> None: ...

    def get_case_study(
        self, repository_id: str, audience: str = DEFAULT_AUDIENCE
    ) -> CaseStudyRecord | None: ...


class SynopsisStore(Protocol):
    def save_synopsis(self, repository_id: str, synopsis: str) -> None: ...

    def get_synopsis(self, repository_id: str) -> str | None: ...


class RepoContextReader(Protocol):
    def get_repo_context(self, repository_id: str) -> str | None: ...


class GithubContextReader(Protocol):
    def get_github_context(
        self,
        *,
        repository_id: str,
        canonical_url: str,
        commit_sha: str,
    ) -> GithubContext | None: ...


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

    def list_analyses_since(
        self, repository_id: str, *, since: str
    ) -> list[TimestampedAnalysis]: ...


class CommitDateReader(Protocol):
    def get_commit_date_map(self, repository_id: str) -> dict[str, str]: ...


class FileEvidenceReader(Protocol):
    def get_file_evidence_commits(
        self, repository_id: str, *, limit: int = 5
    ) -> dict[str, tuple[str, ...]]: ...


class PatternSynthesisClient(Protocol):
    def synthesize(self, report: PatternReport) -> list[PatternExplanation]: ...


# ---------------------------------------------------------------------------
# Repository list port
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepositoryRecord:
    repository_id: str
    canonical_url: str
    status: str
    commit_count: int
    analysis_count: int
    has_case_study: bool


class RepositoryListReader(Protocol):
    def list_repositories(self) -> list[RepositoryRecord]: ...


# ---------------------------------------------------------------------------
# Commit count port (for estimate endpoint)
# ---------------------------------------------------------------------------


class CommitCountReader(Protocol):
    def count_commits(self, repository_id: str) -> int: ...

    def count_analyses(self, repository_id: str) -> int: ...


# ---------------------------------------------------------------------------
# Commit with analysis port (for commits endpoint)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CommitWithAnalysisRecord:
    sha: str
    message: str
    committed_at: str
    analysis_data: str | None
    files_changed: tuple[str, ...] = ()


class CommitWithAnalysisReader(Protocol):
    def list_commits_with_analyses(
        self,
        repository_id: str,
        *,
        limit: int,
        order: str = "newest",
    ) -> list[CommitWithAnalysisRecord]: ...


# ---------------------------------------------------------------------------
# Contributor port
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContributorRecord:
    author_name: str
    commit_count: int
    first_commit: str | None
    last_commit: str | None
    is_bot: bool
    active_days: int
    github_username: str | None
    category_counts: dict[str, int]
    top_files: list[str]


class ContributorReader(Protocol):
    def list_contributors(self, repository_id: str) -> list[ContributorRecord]: ...
