from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from git_it.repository_ingestion.application.ports import (
    CommitExtractor,
    CommitFactWriter,
    DefaultBranchReader,
    DefaultBranchWriter,
    FileFactWriter,
    GitGateway,
    GitGatewayError,
    IngestionRunRecord,
    IngestionRunWriter,
    ProjectDocReader,
    ProjectDocWriter,
)
from git_it.repository_ingestion.domain.failure_mapping import failure_for_error_code
from git_it.repository_ingestion.domain.url_contract import (
    RepositoryUrlValidationError,
    parse_repository_url,
)


@dataclass(frozen=True)
class IngestionResult:
    status: str
    error_code: str | None
    stage: str
    retryable: bool
    safe_message: str | None
    run_id: str | None = None
    canonical_url: str | None = None
    commits_inserted: int | None = None
    commits_reused: int | None = None
    files_inserted: int | None = None
    files_reused: int | None = None


class RepositoryIngestionService:
    def __init__(
        self,
        *,
        git_gateway: GitGateway,
        commit_extractor: CommitExtractor | None = None,
        commit_fact_writer: CommitFactWriter | None = None,
        file_fact_writer: FileFactWriter | None = None,
        repository_id: str | None = None,
        run_writer: IngestionRunWriter | None = None,
        run_id_factory: Callable[[], str] | None = None,
        clock: Callable[[], str] | None = None,
        default_branch_reader: DefaultBranchReader | None = None,
        default_branch_writer: DefaultBranchWriter | None = None,
        project_doc_reader: ProjectDocReader | None = None,
        project_doc_writer: ProjectDocWriter | None = None,
    ) -> None:
        self._git_gateway = git_gateway
        self._commit_extractor = commit_extractor
        self._commit_fact_writer = commit_fact_writer
        self._file_fact_writer = file_fact_writer
        self._repository_id = repository_id
        self._run_writer = run_writer
        self._run_id_factory = run_id_factory or (lambda: f"run-{uuid4().hex}")
        self._clock = clock or (lambda: datetime.now(UTC).isoformat())
        self._default_branch_reader = default_branch_reader
        self._default_branch_writer = default_branch_writer
        self._project_doc_reader = project_doc_reader
        self._project_doc_writer = project_doc_writer

    def ingest(self, raw_url: str) -> IngestionResult:
        run_id = self._next_run_id()
        started_at = self._clock()
        try:
            parsed_url = parse_repository_url(raw_url)
        except RepositoryUrlValidationError as error:
            failure = failure_for_error_code(error.error_code)
            result = IngestionResult(
                status=failure.status,
                error_code=failure.error_code,
                stage=failure.stage,
                retryable=failure.retryable,
                safe_message=error.safe_message,
                run_id=run_id,
            )
            self._persist_run_result(
                result=result,
                canonical_url="",
                started_at=started_at,
                completed_at=self._clock(),
            )
            return result

        try:
            self._git_gateway.clone_or_fetch(parsed_url.canonical_url)
        except GitGatewayError as error:
            failure = failure_for_error_code(error.error_code)
            result = IngestionResult(
                status=failure.status,
                error_code=failure.error_code,
                stage=failure.stage,
                retryable=failure.retryable,
                safe_message=error.safe_message,
                run_id=run_id,
                canonical_url=parsed_url.canonical_url,
            )
            self._persist_run_result(
                result=result,
                canonical_url=parsed_url.canonical_url,
                started_at=started_at,
                completed_at=self._clock(),
            )
            return result

        if self._default_branch_reader is not None:
            default_branch = self._default_branch_reader.read_default_branch()
            if default_branch is not None and self._default_branch_writer is not None:
                self._default_branch_writer.save_default_branch(
                    self._repository_id or "", default_branch
                )

        if self._project_doc_reader is not None:
            project_docs = self._project_doc_reader.get_project_docs(self._repository_id or "")
            if project_docs is not None and self._project_doc_writer is not None:
                self._project_doc_writer.save_project_docs(project_docs)

        commits_inserted: int | None = None
        commits_reused: int | None = None
        files_inserted: int | None = None
        files_reused: int | None = None
        if self._commit_extractor is not None:
            extracted = self._commit_extractor.extract_commits()
            repo_id = self._repository_id or ""
            if self._commit_fact_writer is not None:
                cp = self._commit_fact_writer.save_commit_facts(
                    extracted,
                    repository_id=repo_id,
                )
                commits_inserted = cp.inserted
                commits_reused = cp.reused
            if self._file_fact_writer is not None:
                fp = self._file_fact_writer.save_file_facts(
                    extracted,
                    repository_id=repo_id,
                )
                files_inserted = fp.inserted
                files_reused = fp.reused

        result = IngestionResult(
            status="COMPLETED",
            error_code=None,
            stage="COMPLETED",
            retryable=False,
            safe_message=None,
            run_id=run_id,
            canonical_url=parsed_url.canonical_url,
            commits_inserted=commits_inserted,
            commits_reused=commits_reused,
            files_inserted=files_inserted,
            files_reused=files_reused,
        )
        self._persist_run_result(
            result=result,
            canonical_url=parsed_url.canonical_url,
            started_at=started_at,
            completed_at=self._clock(),
        )
        return result

    def _next_run_id(self) -> str | None:
        if self._run_writer is None:
            return None
        return self._run_id_factory()

    def _persist_run_result(
        self,
        *,
        result: IngestionResult,
        canonical_url: str,
        started_at: str,
        completed_at: str | None,
    ) -> None:
        if self._run_writer is None or result.run_id is None:
            return
        self._run_writer.save_ingestion_run(
            IngestionRunRecord(
                run_id=result.run_id,
                repository_id=self._repository_id or "",
                canonical_url=canonical_url,
                status=result.status,
                started_at=started_at,
                completed_at=completed_at,
                error_code=result.error_code,
                error_stage=result.stage if result.error_code is not None else None,
                retryable=result.retryable if result.error_code is not None else None,
                safe_message=result.safe_message,
            )
        )
