from pathlib import Path

from git_it.repository_ingestion.application.commit_analysis_service import CommitAnalysisService
from git_it.repository_ingestion.application.commit_query_service import CommitRecord
from git_it.repository_ingestion.application.ports import CaseStudyRecord, LLMMessage
from git_it.repository_ingestion.domain.analysis import (
    CommitAnalysis,
    CommitCategory,
    RiskLevel,
)
from git_it.repository_ingestion.infrastructure.sqlite import SqliteCaseStudyStore
from tests.unit.fakes import FakeCommitReader

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _make_record(
    sha: str = "abc1234",
    message: str = "Add feature",
    author: str = "Alice",
) -> CommitRecord:
    return CommitRecord(
        repository_id="repo-1",
        sha=sha,
        committed_at="2026-01-01T00:00:00+00:00",
        message=message,
        author_name=author,
        committer_name=author,
        parent_shas=(),
    )


def _make_analysis(sha: str = "abc1234") -> CommitAnalysis:
    return CommitAnalysis(
        commit_sha=sha,
        summary="Added a feature",
        category=CommitCategory.FEATURE,
        intent=None,
        intent_is_inferred=True,
        affected_components=["core"],
        risk_level=RiskLevel.LOW,
        confidence=0.7,
        evidence=[],
        limitations=[],
    )


class FakeCommitAnalysisClient:
    def __init__(self, response: CommitAnalysis | None = None) -> None:
        self._response = response or _make_analysis()
        self.calls: list[tuple[str, list[LLMMessage]]] = []

    def analyze_commit(self, system: str, messages: list[LLMMessage]) -> CommitAnalysis:
        self.calls.append((system, list(messages)))
        return self._response


class FakeRepoContextReader:
    def __init__(self, context: str | None = None) -> None:
        self._context = context
        self.calls: list[str] = []

    def get_repo_context(self, repository_id: str) -> str | None:
        self.calls.append(repository_id)
        return self._context


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_context_when_reader_is_none() -> None:
    client = FakeCommitAnalysisClient()
    service = CommitAnalysisService(
        reader=FakeCommitReader(),
        client=client,
        repo_context_reader=None,
    )
    service.analyze_commit(_make_record())
    _system, messages = client.calls[0]
    user_msgs = [m for m in messages if m.role == "user"]
    assert user_msgs
    assert "REPO CONTEXT" not in user_msgs[0].content


def test_no_context_when_reader_returns_none() -> None:
    client = FakeCommitAnalysisClient()
    service = CommitAnalysisService(
        reader=FakeCommitReader(),
        client=client,
        repo_context_reader=FakeRepoContextReader(context=None),
    )
    service.analyze_commit(_make_record())
    _system, messages = client.calls[0]
    user_msgs = [m for m in messages if m.role == "user"]
    assert user_msgs
    assert "REPO CONTEXT" not in user_msgs[0].content


def test_context_injected_into_user_message() -> None:
    client = FakeCommitAnalysisClient()
    service = CommitAnalysisService(
        reader=FakeCommitReader(),
        client=client,
        repo_context_reader=FakeRepoContextReader(context="This is a Go MCP server."),
    )
    service.analyze_commit(_make_record())
    _system, messages = client.calls[0]
    user_msgs = [m for m in messages if m.role == "user"]
    assert user_msgs
    assert "This is a Go MCP server." in user_msgs[0].content


def test_context_appears_in_user_role_not_system_role() -> None:
    client = FakeCommitAnalysisClient()
    service = CommitAnalysisService(
        reader=FakeCommitReader(),
        client=client,
        repo_context_reader=FakeRepoContextReader(context="Go MCP server context"),
    )
    service.analyze_commit(_make_record())
    system, messages = client.calls[0]
    user_msgs = [m for m in messages if m.role == "user"]
    assert user_msgs
    assert "Go MCP server context" in user_msgs[0].content
    # repo_context must NOT be concatenated into the system prompt
    assert "Go MCP server context" not in system


def test_context_fetched_once_for_multiple_commits() -> None:
    records = [_make_record("sha1"), _make_record("sha2"), _make_record("sha3")]
    repo_reader = FakeRepoContextReader(context="Some background")
    service = CommitAnalysisService(
        reader=FakeCommitReader(records),
        client=FakeCommitAnalysisClient(),
        repo_context_reader=repo_reader,
    )
    service.analyze_commits("repo-1")
    assert len(repo_reader.calls) == 1


def test_all_commits_receive_same_context() -> None:
    records = [_make_record("sha1"), _make_record("sha2")]
    client = FakeCommitAnalysisClient()
    service = CommitAnalysisService(
        reader=FakeCommitReader(records),
        client=client,
        repo_context_reader=FakeRepoContextReader(context="Shared context text"),
    )
    service.analyze_commits("repo-1")
    assert len(client.calls) == 2
    for _system, messages in client.calls:
        user_msgs = [m for m in messages if m.role == "user"]
        assert user_msgs
        assert "Shared context text" in user_msgs[0].content


def test_analyze_commit_without_context_is_unchanged() -> None:
    client = FakeCommitAnalysisClient()
    service = CommitAnalysisService(
        reader=FakeCommitReader(),
        client=client,
    )
    service.analyze_commit(_make_record())
    _system, messages = client.calls[0]
    user_msgs = [m for m in messages if m.role == "user"]
    assert user_msgs
    assert "REPO CONTEXT" not in user_msgs[0].content


def test_analyze_commit_with_explicit_context() -> None:
    client = FakeCommitAnalysisClient()
    service = CommitAnalysisService(
        reader=FakeCommitReader(),
        client=client,
    )
    service.analyze_commit(_make_record(), repo_context="context text")
    _system, messages = client.calls[0]
    user_msgs = [m for m in messages if m.role == "user"]
    assert user_msgs
    assert "context text" in user_msgs[0].content


def test_context_truncation_applied_by_reader(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    store = SqliteCaseStudyStore(db_path)
    store.initialize()
    long_narrative = "y" * 5000
    store.save_case_study(
        CaseStudyRecord(
            repository_id="repo-x",
            narrative=long_narrative,
            commit_count=1,
            hotspot_count=0,
        )
    )
    result = store.get_repo_context("repo-x")
    assert result is not None
    assert len(result) <= 2000
