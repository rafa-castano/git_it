from datetime import UTC, datetime

import pytest

from git_it.repository_ingestion.application.ports import (
    CommitPersistenceResult,
    ExtractedCommit,
    GitGatewayError,
    IngestionRunRecord,
    ProjectDocContent,
)
from git_it.repository_ingestion.application.service import RepositoryIngestionService


class SpyGitGateway:
    def __init__(self) -> None:
        self.clone_or_fetch_calls: list[str] = []

    def clone_or_fetch(self, canonical_url: str) -> None:
        self.clone_or_fetch_calls.append(canonical_url)


class FailingGitGateway:
    def __init__(self, *, error_code: str) -> None:
        self.error_code = error_code
        self.clone_or_fetch_calls: list[str] = []

    def clone_or_fetch(self, canonical_url: str) -> None:
        self.clone_or_fetch_calls.append(canonical_url)
        raise GitGatewayError(error_code=self.error_code)


class RecordingIngestionRunWriter:
    def __init__(self) -> None:
        self.records: list[IngestionRunRecord] = []

    def save_ingestion_run(self, record: IngestionRunRecord) -> None:
        self.records.append(record)


@pytest.mark.parametrize(
    ("raw_url", "expected_error_code"),
    [
        ("not-a-url", "INVALID_URL"),
        ("https://gitlab.com/owner/repo", "UNSUPPORTED_URL"),
    ],
)
def test_ingestion_service_returns_validation_failure_without_git_tooling(
    raw_url: str,
    expected_error_code: str,
) -> None:
    git_gateway = SpyGitGateway()
    service = RepositoryIngestionService(git_gateway=git_gateway)

    result = service.ingest(raw_url)

    assert result.status == "FAILED_VALIDATION"
    assert result.error_code == expected_error_code
    assert result.stage == "VALIDATING_URL"
    assert result.retryable is False
    assert result.safe_message == "Repository URL must be a public GitHub HTTPS repository URL."
    assert git_gateway.clone_or_fetch_calls == []


@pytest.mark.parametrize(
    "raw_url",
    [
        "https://github.com/owner/repo",
        "https://github.com/owner/repo.git",
    ],
)
def test_ingestion_service_starts_clone_or_fetch_with_canonical_url(raw_url: str) -> None:
    git_gateway = SpyGitGateway()
    service = RepositoryIngestionService(git_gateway=git_gateway)

    result = service.ingest(raw_url)

    assert result.status == "COMPLETED"
    assert result.error_code is None
    assert result.stage == "COMPLETED"
    assert result.retryable is False
    assert result.safe_message is None
    assert git_gateway.clone_or_fetch_calls == ["https://github.com/owner/repo"]


@pytest.mark.parametrize(
    ("error_code", "expected_stage", "expected_retryable"),
    [
        ("REPOSITORY_NOT_FOUND", "FETCHING_METADATA", False),
        ("REPOSITORY_PRIVATE_OR_INACCESSIBLE", "FETCHING_METADATA", False),
        ("METADATA_UNAVAILABLE", "FETCHING_METADATA", True),
        ("CLONE_TIMEOUT", "CLONING_OR_FETCHING", True),
        ("GIT_FETCH_FAILED", "CLONING_OR_FETCHING", True),
    ],
)
def test_ingestion_service_maps_known_git_gateway_failures_to_safe_failure_result(
    error_code: str,
    expected_stage: str,
    expected_retryable: bool,
) -> None:
    git_gateway = FailingGitGateway(error_code=error_code)
    service = RepositoryIngestionService(git_gateway=git_gateway)

    result = service.ingest("https://github.com/owner/repo")

    assert result.status == "FAILED_FETCH"
    assert result.error_code == error_code
    assert result.stage == expected_stage
    assert result.retryable is expected_retryable
    assert result.safe_message == "Repository fetch failed safely before analysis could start."
    assert git_gateway.clone_or_fetch_calls == ["https://github.com/owner/repo"]


def _make_commit(sha: str) -> ExtractedCommit:
    return ExtractedCommit(
        sha=sha,
        committed_at="2026-01-01T00:00:00Z",
        message="test commit",
        author_name="Author",
        committer_name="Committer",
        parent_shas=(),
    )


def test_ingestion_service_calls_extractor_after_successful_clone_or_fetch() -> None:
    git_gateway = SpyGitGateway()

    class FakeCommitExtractor:
        def __init__(self) -> None:
            self.call_count = 0

        def extract_commits(self) -> list[ExtractedCommit]:
            self.call_count += 1
            return [_make_commit("sha1"), _make_commit("sha2"), _make_commit("sha3")]

    extractor = FakeCommitExtractor()
    service = RepositoryIngestionService(
        git_gateway=git_gateway,
        commit_extractor=extractor,
    )

    service.ingest("https://github.com/owner/repo")

    assert extractor.call_count == 1


def test_ingestion_service_persists_commits_and_reports_inserted_reused() -> None:
    git_gateway = SpyGitGateway()

    class FakeCommitExtractor:
        def extract_commits(self) -> list[ExtractedCommit]:
            return [_make_commit("sha1"), _make_commit("sha2"), _make_commit("sha3")]

    class FakeCommitFactWriter:
        def save_commit_facts(
            self, commits: list[ExtractedCommit], *, repository_id: str
        ) -> CommitPersistenceResult:
            return CommitPersistenceResult(inserted=2, reused=1)

    service = RepositoryIngestionService(
        git_gateway=git_gateway,
        commit_extractor=FakeCommitExtractor(),
        commit_fact_writer=FakeCommitFactWriter(),
        repository_id="repo-1",
    )

    result = service.ingest("https://github.com/owner/repo")

    assert result.commits_inserted == 2
    assert result.commits_reused == 1


def test_ingestion_service_does_not_report_counts_without_fact_writer() -> None:
    git_gateway = SpyGitGateway()

    class FakeCommitExtractor:
        def extract_commits(self) -> list[ExtractedCommit]:
            return [_make_commit("sha1")]

    service = RepositoryIngestionService(
        git_gateway=git_gateway,
        commit_extractor=FakeCommitExtractor(),
    )

    result = service.ingest("https://github.com/owner/repo")

    assert result.commits_inserted is None
    assert result.commits_reused is None


def test_ingestion_service_skips_extraction_when_no_extractor_is_wired() -> None:
    git_gateway = SpyGitGateway()
    service = RepositoryIngestionService(git_gateway=git_gateway)

    result = service.ingest("https://github.com/owner/repo")

    assert result.commits_inserted is None
    assert result.commits_reused is None


def test_ingestion_service_does_not_extract_commits_on_gateway_failure() -> None:
    class FakeCommitExtractor:
        def __init__(self) -> None:
            self.call_count = 0

        def extract_commits(self) -> list[ExtractedCommit]:
            self.call_count += 1
            return []

    extractor = FakeCommitExtractor()
    git_gateway = FailingGitGateway(error_code="CLONE_TIMEOUT")
    service = RepositoryIngestionService(
        git_gateway=git_gateway,
        commit_extractor=extractor,
    )

    service.ingest("https://github.com/owner/repo")

    assert extractor.call_count == 0


def test_ingestion_service_includes_canonical_url_in_success_like_result() -> None:
    git_gateway = SpyGitGateway()
    service = RepositoryIngestionService(git_gateway=git_gateway)

    result = service.ingest("https://github.com/owner/repo")

    assert result.canonical_url == "https://github.com/owner/repo"


def test_ingestion_service_normalizes_canonical_url_by_stripping_git_suffix() -> None:
    git_gateway = SpyGitGateway()
    service = RepositoryIngestionService(git_gateway=git_gateway)

    result = service.ingest("https://github.com/owner/repo.git")

    assert result.canonical_url == "https://github.com/owner/repo"


def test_ingestion_service_canonical_url_is_none_for_validation_failure() -> None:
    git_gateway = SpyGitGateway()
    service = RepositoryIngestionService(git_gateway=git_gateway)

    result = service.ingest("not-a-url")

    assert result.canonical_url is None


def test_ingestion_service_persists_success_like_run_result() -> None:
    git_gateway = SpyGitGateway()
    run_writer = RecordingIngestionRunWriter()
    service = RepositoryIngestionService(
        git_gateway=git_gateway,
        repository_id="repo-1",
        run_writer=run_writer,
        run_id_factory=lambda: "run-1",
        clock=lambda: "2026-06-15T10:00:00Z",
    )

    result = service.ingest("https://github.com/owner/repo.git")

    assert result.run_id == "run-1"
    assert run_writer.records == [
        IngestionRunRecord(
            run_id="run-1",
            repository_id="repo-1",
            canonical_url="https://github.com/owner/repo",
            status="COMPLETED",
            started_at="2026-06-15T10:00:00Z",
            completed_at="2026-06-15T10:00:00Z",
            error_code=None,
            error_stage=None,
            retryable=None,
            safe_message=None,
        )
    ]


def test_ingestion_service_persists_validation_failure_without_raw_invalid_url() -> None:
    git_gateway = SpyGitGateway()
    run_writer = RecordingIngestionRunWriter()
    service = RepositoryIngestionService(
        git_gateway=git_gateway,
        repository_id="repo-1",
        run_writer=run_writer,
        run_id_factory=lambda: "run-1",
        clock=lambda: "2026-06-15T10:00:00Z",
    )

    result = service.ingest("https://token@github.com/owner/repo")

    assert result.run_id == "run-1"
    assert run_writer.records == [
        IngestionRunRecord(
            run_id="run-1",
            repository_id="repo-1",
            canonical_url="",
            status="FAILED_VALIDATION",
            started_at="2026-06-15T10:00:00Z",
            completed_at="2026-06-15T10:00:00Z",
            error_code="UNSUPPORTED_URL",
            error_stage="VALIDATING_URL",
            retryable=False,
            safe_message="Repository URL must be a public GitHub HTTPS repository URL.",
        )
    ]
    assert "token" not in run_writer.records[0].canonical_url


def test_ingestion_service_persists_file_facts_and_reports_counts() -> None:
    git_gateway = SpyGitGateway()

    class FakeCommitExtractor:
        def extract_commits(self) -> list[ExtractedCommit]:
            return [_make_commit("sha1"), _make_commit("sha2")]

    class FakeCommitFactWriter:
        def save_commit_facts(
            self, commits: list[ExtractedCommit], *, repository_id: str
        ) -> CommitPersistenceResult:
            return CommitPersistenceResult(inserted=2, reused=0)

    class FakeFileFactWriter:
        def save_file_facts(
            self, commits: list[ExtractedCommit], *, repository_id: str
        ) -> CommitPersistenceResult:
            return CommitPersistenceResult(inserted=5, reused=1)

    service = RepositoryIngestionService(
        git_gateway=git_gateway,
        commit_extractor=FakeCommitExtractor(),
        commit_fact_writer=FakeCommitFactWriter(),
        file_fact_writer=FakeFileFactWriter(),
        repository_id="repo-1",
    )

    result = service.ingest("https://github.com/owner/repo")

    assert result.files_inserted == 5
    assert result.files_reused == 1


def test_ingestion_service_does_not_report_file_counts_without_file_fact_writer() -> None:
    git_gateway = SpyGitGateway()

    class FakeCommitExtractor:
        def extract_commits(self) -> list[ExtractedCommit]:
            return [_make_commit("sha1")]

    service = RepositoryIngestionService(
        git_gateway=git_gateway,
        commit_extractor=FakeCommitExtractor(),
    )

    result = service.ingest("https://github.com/owner/repo")

    assert result.files_inserted is None
    assert result.files_reused is None


# ---------------------------------------------------------------------------
# Default branch capture (spec 020)
# ---------------------------------------------------------------------------


class FakeDefaultBranchReader:
    def __init__(self, *, branch: str | None) -> None:
        self.branch = branch
        self.call_count = 0

    def read_default_branch(self) -> str | None:
        self.call_count += 1
        return self.branch


class RecordingDefaultBranchWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def save_default_branch(self, repository_id: str, default_branch: str) -> None:
        self.calls.append((repository_id, default_branch))


def test_ingestion_service_persists_default_branch_after_successful_clone() -> None:
    git_gateway = SpyGitGateway()
    reader = FakeDefaultBranchReader(branch="main")
    writer = RecordingDefaultBranchWriter()
    service = RepositoryIngestionService(
        git_gateway=git_gateway,
        repository_id="repo-1",
        default_branch_reader=reader,
        default_branch_writer=writer,
    )

    service.ingest("https://github.com/owner/repo")

    assert reader.call_count == 1
    assert writer.calls == [("repo-1", "main")]


def test_ingestion_service_does_not_persist_default_branch_when_reader_returns_none() -> None:
    git_gateway = SpyGitGateway()
    reader = FakeDefaultBranchReader(branch=None)
    writer = RecordingDefaultBranchWriter()
    service = RepositoryIngestionService(
        git_gateway=git_gateway,
        repository_id="repo-1",
        default_branch_reader=reader,
        default_branch_writer=writer,
    )

    service.ingest("https://github.com/owner/repo")

    assert writer.calls == []


def test_ingestion_service_skips_default_branch_reader_without_wiring() -> None:
    git_gateway = SpyGitGateway()
    service = RepositoryIngestionService(git_gateway=git_gateway, repository_id="repo-1")

    result = service.ingest("https://github.com/owner/repo")

    assert result.status == "COMPLETED"


def test_ingestion_service_does_not_read_default_branch_on_gateway_failure() -> None:
    git_gateway = FailingGitGateway(error_code="CLONE_TIMEOUT")
    reader = FakeDefaultBranchReader(branch="main")
    writer = RecordingDefaultBranchWriter()
    service = RepositoryIngestionService(
        git_gateway=git_gateway,
        repository_id="repo-1",
        default_branch_reader=reader,
        default_branch_writer=writer,
    )

    service.ingest("https://github.com/owner/repo")

    assert reader.call_count == 0
    assert writer.calls == []


def test_ingestion_service_persists_git_gateway_failure() -> None:
    git_gateway = FailingGitGateway(error_code="CLONE_TIMEOUT")
    run_writer = RecordingIngestionRunWriter()
    service = RepositoryIngestionService(
        git_gateway=git_gateway,
        repository_id="repo-1",
        run_writer=run_writer,
        run_id_factory=lambda: "run-1",
        clock=lambda: "2026-06-15T10:00:00Z",
    )

    result = service.ingest("https://github.com/owner/repo")

    assert result.run_id == "run-1"
    assert run_writer.records == [
        IngestionRunRecord(
            run_id="run-1",
            repository_id="repo-1",
            canonical_url="https://github.com/owner/repo",
            status="FAILED_FETCH",
            started_at="2026-06-15T10:00:00Z",
            completed_at="2026-06-15T10:00:00Z",
            error_code="CLONE_TIMEOUT",
            error_stage="CLONING_OR_FETCHING",
            retryable=True,
            safe_message="Repository fetch failed safely before analysis could start.",
        )
    ]


# ---------------------------------------------------------------------------
# File-tree capture (spec 029)
# ---------------------------------------------------------------------------


class FakeFileTreeReader:
    def __init__(self, *, paths: list[str]) -> None:
        self.paths = paths
        self.call_count = 0

    def read_file_paths(self) -> list[str]:
        self.call_count += 1
        return self.paths


class RecordingFileTreeWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def save_file_paths(self, repository_id: str, paths: list[str]) -> None:
        self.calls.append((repository_id, paths))


def test_ingestion_service_persists_file_tree_after_successful_clone() -> None:
    git_gateway = SpyGitGateway()
    reader = FakeFileTreeReader(paths=["README.md", "src/app.py"])
    writer = RecordingFileTreeWriter()
    service = RepositoryIngestionService(
        git_gateway=git_gateway,
        repository_id="repo-1",
        file_tree_reader=reader,
        file_tree_writer=writer,
    )

    service.ingest("https://github.com/owner/repo")

    assert reader.call_count == 1
    assert writer.calls == [("repo-1", ["README.md", "src/app.py"])]


def test_ingestion_service_saves_empty_file_tree_snapshot() -> None:
    git_gateway = SpyGitGateway()
    reader = FakeFileTreeReader(paths=[])
    writer = RecordingFileTreeWriter()
    service = RepositoryIngestionService(
        git_gateway=git_gateway,
        repository_id="repo-1",
        file_tree_reader=reader,
        file_tree_writer=writer,
    )

    service.ingest("https://github.com/owner/repo")

    assert reader.call_count == 1
    assert writer.calls == [("repo-1", [])]


def test_ingestion_service_skips_file_tree_reader_without_wiring() -> None:
    git_gateway = SpyGitGateway()
    service = RepositoryIngestionService(git_gateway=git_gateway, repository_id="repo-1")

    result = service.ingest("https://github.com/owner/repo")

    assert result.status == "COMPLETED"


def test_ingestion_service_does_not_read_file_tree_on_gateway_failure() -> None:
    git_gateway = FailingGitGateway(error_code="CLONE_TIMEOUT")
    reader = FakeFileTreeReader(paths=["README.md"])
    writer = RecordingFileTreeWriter()
    service = RepositoryIngestionService(
        git_gateway=git_gateway,
        repository_id="repo-1",
        file_tree_reader=reader,
        file_tree_writer=writer,
    )

    service.ingest("https://github.com/owner/repo")

    assert reader.call_count == 0
    assert writer.calls == []


def test_ingestion_service_does_not_write_file_tree_without_writer() -> None:
    git_gateway = SpyGitGateway()
    reader = FakeFileTreeReader(paths=["README.md"])
    service = RepositoryIngestionService(
        git_gateway=git_gateway,
        repository_id="repo-1",
        file_tree_reader=reader,
    )

    result = service.ingest("https://github.com/owner/repo")

    # Reader is invoked, but with no writer wired nothing is persisted and the
    # ingestion still completes cleanly.
    assert reader.call_count == 1
    assert result.status == "COMPLETED"


# ---------------------------------------------------------------------------
# Project-doc capture (spec 025)
# ---------------------------------------------------------------------------


def _make_project_docs(repository_id: str) -> ProjectDocContent:
    return ProjectDocContent(
        repository_id=repository_id,
        readme_text="# Example\nThis project does things.",
        readme_truncated=False,
        changelog_text=None,
        changelog_truncated=False,
        captured_at=datetime(2026, 6, 15, 10, 0, 0, tzinfo=UTC),
    )


class FakeProjectDocReader:
    def __init__(self, *, content: ProjectDocContent | None) -> None:
        self.content = content
        self.calls: list[str] = []

    def get_project_docs(self, repository_id: str) -> ProjectDocContent | None:
        self.calls.append(repository_id)
        return self.content


class RecordingProjectDocWriter:
    def __init__(self) -> None:
        self.calls: list[ProjectDocContent] = []

    def save_project_docs(self, content: ProjectDocContent) -> None:
        self.calls.append(content)


def test_ingestion_service_persists_project_docs_after_successful_clone() -> None:
    git_gateway = SpyGitGateway()
    project_docs = _make_project_docs("repo-1")
    reader = FakeProjectDocReader(content=project_docs)
    writer = RecordingProjectDocWriter()
    service = RepositoryIngestionService(
        git_gateway=git_gateway,
        repository_id="repo-1",
        project_doc_reader=reader,
        project_doc_writer=writer,
    )

    service.ingest("https://github.com/owner/repo")

    assert reader.calls == ["repo-1"]
    assert writer.calls == [project_docs]


def test_ingestion_service_does_not_persist_project_docs_when_reader_returns_none() -> None:
    git_gateway = SpyGitGateway()
    reader = FakeProjectDocReader(content=None)
    writer = RecordingProjectDocWriter()
    service = RepositoryIngestionService(
        git_gateway=git_gateway,
        repository_id="repo-1",
        project_doc_reader=reader,
        project_doc_writer=writer,
    )

    service.ingest("https://github.com/owner/repo")

    assert writer.calls == []


def test_ingestion_service_skips_project_doc_reader_without_wiring() -> None:
    git_gateway = SpyGitGateway()
    service = RepositoryIngestionService(git_gateway=git_gateway, repository_id="repo-1")

    result = service.ingest("https://github.com/owner/repo")

    assert result.status == "COMPLETED"


def test_ingestion_service_does_not_read_project_docs_on_gateway_failure() -> None:
    git_gateway = FailingGitGateway(error_code="CLONE_TIMEOUT")
    reader = FakeProjectDocReader(content=_make_project_docs("repo-1"))
    writer = RecordingProjectDocWriter()
    service = RepositoryIngestionService(
        git_gateway=git_gateway,
        repository_id="repo-1",
        project_doc_reader=reader,
        project_doc_writer=writer,
    )

    service.ingest("https://github.com/owner/repo")

    assert reader.calls == []
    assert writer.calls == []
