from pathlib import Path

import git
import pytest

from git_it.repository_ingestion.application.embedding_service import EmbeddingService
from git_it.repository_ingestion.application.ports import ExtractedCommit, LLMMessage
from git_it.repository_ingestion.composition import (
    build_commit_analysis_service,
    build_discussion_summarizer,
    build_embedding_client,
    build_narrative_service,
    build_repository_ingestion_service,
)
from git_it.repository_ingestion.domain.analysis import CommitAnalysis, CommitCategory, RiskLevel
from git_it.repository_ingestion.infrastructure.git import GitCommandPlan, GitCommandResult
from git_it.repository_ingestion.infrastructure.llm import LiteLLMEmbeddingClient, LiteLLMLLMClient
from git_it.repository_ingestion.infrastructure.sqlite import SqliteIngestionRunStore
from git_it.repository_ingestion.infrastructure.workspace import ingestion_workspace_root


class RecordingGitCommandRunner:
    def __init__(self) -> None:
        self.plans: list[GitCommandPlan] = []

    def run(self, plan: GitCommandPlan) -> GitCommandResult:
        self.plans.append(plan)
        return GitCommandResult(exit_code=0)


class NullCommitExtractor:
    def extract_commits(self) -> list[ExtractedCommit]:
        return []


def test_build_repository_ingestion_service_wires_safe_git_gateway_to_workspace_cache(
    tmp_path: Path,
) -> None:
    runner = RecordingGitCommandRunner()
    service = build_repository_ingestion_service(
        project_root=tmp_path,
        repository_id="repo-123",
        runner=runner,
        commit_extractor=NullCommitExtractor(),
    )

    result = service.ingest("https://github.com/owner/repo.git")

    assert result.status == "COMPLETED"
    assert len(runner.plans) == 1
    assert runner.plans[0].args == [
        "git",
        "-c",
        "protocol.file.allow=never",
        "clone",
        "--bare",
        "--no-checkout",
        "--no-recurse-submodules",
        "https://github.com/owner/repo",
        str(tmp_path / ".data" / "git-it" / "ingestion" / "repos" / "repo-123.git"),
    ]


def test_build_repository_ingestion_service_reuses_existing_bare_cache(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / ".data" / "git-it" / "ingestion" / "repos" / "repo-123.git"
    cache_path.mkdir(parents=True)
    runner = RecordingGitCommandRunner()
    service = build_repository_ingestion_service(
        project_root=tmp_path,
        repository_id="repo-123",
        runner=runner,
        commit_extractor=NullCommitExtractor(),
    )

    result = service.ingest("https://github.com/owner/repo")

    assert result.status == "COMPLETED"
    assert len(runner.plans) == 1
    assert runner.plans[0].args == [
        "git",
        "--git-dir",
        str(cache_path),
        "-c",
        "protocol.file.allow=never",
        "fetch",
        "--prune",
        "--tags",
        "--no-recurse-submodules",
        "origin",
        "+refs/heads/*:refs/heads/*",
        "+refs/tags/*:refs/tags/*",
    ]


def test_build_repository_ingestion_service_wires_default_sqlite_run_store(
    tmp_path: Path,
) -> None:
    runner = RecordingGitCommandRunner()
    service = build_repository_ingestion_service(
        project_root=tmp_path,
        repository_id="repo-123",
        runner=runner,
        commit_extractor=NullCommitExtractor(),
    )

    result = service.ingest("https://github.com/owner/repo")

    store = SqliteIngestionRunStore(ingestion_workspace_root(tmp_path) / "git-it.sqlite3")
    runs = store.list_ingestion_runs_for_repository("repo-123")
    assert result.run_id is not None
    assert len(runs) == 1
    assert runs[0].run_id == result.run_id
    assert runs[0].repository_id == "repo-123"
    assert runs[0].canonical_url == "https://github.com/owner/repo"
    assert runs[0].status == "COMPLETED"


def test_build_repository_ingestion_service_wires_gitpython_extractor_by_default(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source_repo = git.Repo.init(str(source))
    with source_repo.config_writer() as cfg:
        cfg.set_value("user", "name", "Test Author")
        cfg.set_value("user", "email", "test@example.com")
    (source / "README.md").write_text("hello")
    source_repo.index.add(["README.md"])
    source_repo.index.commit("initial commit")
    (source / "b.txt").write_text("second")
    source_repo.index.add(["b.txt"])
    source_repo.index.commit("second commit")

    cache_path = tmp_path / ".data" / "git-it" / "ingestion" / "repos" / "repo-123.git"
    source_repo.clone(str(cache_path), bare=True)

    runner = RecordingGitCommandRunner()
    service = build_repository_ingestion_service(
        project_root=tmp_path,
        repository_id="repo-123",
        runner=runner,
    )

    result = service.ingest("https://github.com/owner/repo")

    assert result.commits_inserted == 2
    assert result.commits_reused == 0
    assert result.files_inserted is not None
    assert result.files_inserted >= 2


# ---------------------------------------------------------------------------
# Batch 117 — spec 024 open question #2: LiteLLMLLMClient is reused for both
# narrative generation and discussion summarization. Each composition factory
# must construct it with the correct call_site so observe_llm_call's log
# records are attributable to the right purpose.
# ---------------------------------------------------------------------------


def test_build_narrative_service_wires_narrative_generation_call_site(tmp_path: Path) -> None:
    service = build_narrative_service(project_root=tmp_path, model="fake-model")

    llm_client = service._llm_client
    assert isinstance(llm_client, LiteLLMLLMClient)
    assert llm_client._call_site == "narrative_generation"


def test_build_discussion_summarizer_wires_discussion_summarization_call_site() -> None:
    summarizer = build_discussion_summarizer(model="fake-model")

    llm_client = summarizer._llm_client
    assert isinstance(llm_client, LiteLLMLLMClient)
    assert llm_client._call_site == "discussion_summarization"


# ---------------------------------------------------------------------------
# Batch 119 — spec 023: build_embedding_client() is the single source of
# truth for "is the RAG feature available." It must return None when
# OPENAI_API_KEY is absent, and a real LiteLLMEmbeddingClient when present.
# ---------------------------------------------------------------------------


def test_build_embedding_client_returns_none_when_openai_api_key_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert build_embedding_client() is None


def test_build_embedding_client_returns_litellm_client_when_openai_api_key_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-test-key")

    client = build_embedding_client()

    assert isinstance(client, LiteLLMEmbeddingClient)


# ---------------------------------------------------------------------------
# Batch 122 — build_commit_analysis_service wires embedding dependencies
# when OPENAI_API_KEY is set, and hides the feature entirely when absent (spec 023).
# ---------------------------------------------------------------------------


class _StubCommitAnalysisClient:
    def analyze_commit(
        self, system: str, messages: list[LLMMessage]
    ) -> CommitAnalysis:  # pragma: no cover
        return CommitAnalysis(
            commit_sha="stub-sha",
            summary="stub summary",
            category=CommitCategory.CHORE,
            confidence=0.5,
            risk_level=RiskLevel.LOW,
            evidence=[],
            limitations=[],
        )


def test_build_commit_analysis_service_wires_embedding_dependencies_when_key_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-test-key")

    service = build_commit_analysis_service(
        project_root=tmp_path,
        model="fake-model",
        client=_StubCommitAnalysisClient(),
    )

    assert isinstance(service._embedding_service, EmbeddingService)
    assert service._embedding_writer is not None


def test_build_commit_analysis_service_embedding_dependencies_none_when_key_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    service = build_commit_analysis_service(
        project_root=tmp_path,
        model="fake-model",
        client=_StubCommitAnalysisClient(),
    )

    assert service._embedding_service is None
    assert service._embedding_writer is None
