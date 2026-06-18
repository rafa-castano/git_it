"""Service-level integration tests for GitHub context enrichment wiring.

Verifies that:
- github_context_reader is called once per commit (not once per repo).
- canonical_url is passed correctly to the reader.
- When canonical_url is None, the reader is not called.
- Existing service behavior without a github_context_reader is unchanged.
"""

from git_it.repository_ingestion.application.commit_analysis_service import CommitAnalysisService
from git_it.repository_ingestion.application.commit_query_service import CommitRecord
from git_it.repository_ingestion.application.ports import LLMMessage
from git_it.repository_ingestion.domain.analysis import (
    CommitAnalysis,
    CommitCategory,
    RiskLevel,
)
from git_it.repository_ingestion.domain.github_context import GithubContext
from tests.unit.fakes import FakeCommitReader

_CANONICAL = "https://github.com/owner/repo"


def _make_record(sha: str = "abc1234", message: str = "feat: add feature") -> CommitRecord:
    return CommitRecord(
        repository_id="repo-1",
        sha=sha,
        committed_at="2026-01-01T00:00:00+00:00",
        message=message,
        author_name="Alice",
        committer_name="Alice",
        parent_shas=(),
    )


def _make_analysis(sha: str = "abc1234") -> CommitAnalysis:
    return CommitAnalysis(
        commit_sha=sha,
        summary="summary",
        category=CommitCategory.FEATURE,
        intent=None,
        intent_is_inferred=True,
        affected_components=[],
        risk_level=RiskLevel.LOW,
        confidence=0.9,
        evidence=[],
        limitations=[],
    )


class FakeCommitAnalysisClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[LLMMessage]]] = []

    def analyze_commit(self, system: str, messages: list[LLMMessage]) -> CommitAnalysis:
        self.calls.append((system, list(messages)))
        return _make_analysis()


class TrackingGithubContextReader:
    """Records every call made to get_github_context."""

    def __init__(self, context: GithubContext | None = None) -> None:
        self._context = context
        self.calls: list[dict] = []

    def get_github_context(
        self, *, repository_id: str, canonical_url: str, commit_sha: str
    ) -> GithubContext | None:
        self.calls.append(
            {
                "repository_id": repository_id,
                "canonical_url": canonical_url,
                "commit_sha": commit_sha,
            }
        )
        return self._context


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_github_context_fetched_per_commit_not_per_repo() -> None:
    """The reader must be called once per commit, not once for the batch."""
    records = [
        _make_record("sha1", "feat: one"),
        _make_record("sha2", "feat: two"),
        _make_record("sha3", "feat: three"),
    ]
    reader = TrackingGithubContextReader()
    service = CommitAnalysisService(
        reader=FakeCommitReader(records),
        client=FakeCommitAnalysisClient(),
        github_context_reader=reader,
    )
    service.analyze_commits("repo-1", canonical_url=_CANONICAL)
    assert len(reader.calls) == 3


def test_github_context_reader_called_with_canonical_url() -> None:
    """The reader must receive the canonical_url passed to analyze_commits."""
    records = [_make_record("sha1", "feat: feature")]
    reader = TrackingGithubContextReader()
    service = CommitAnalysisService(
        reader=FakeCommitReader(records),
        client=FakeCommitAnalysisClient(),
        github_context_reader=reader,
    )
    service.analyze_commits("repo-1", canonical_url=_CANONICAL)
    assert len(reader.calls) == 1
    assert reader.calls[0]["canonical_url"] == _CANONICAL
    assert reader.calls[0]["commit_sha"] == "sha1"


def test_analyze_commits_with_canonical_url_none_skips_enrichment() -> None:
    """When canonical_url=None, the github_context_reader must NOT be called."""
    records = [_make_record("sha1", "feat: feature")]
    reader = TrackingGithubContextReader()
    service = CommitAnalysisService(
        reader=FakeCommitReader(records),
        client=FakeCommitAnalysisClient(),
        github_context_reader=reader,
    )
    service.analyze_commits("repo-1", canonical_url=None)
    assert len(reader.calls) == 0


def test_existing_tests_unaffected_without_github_reader() -> None:
    """Service without github_context_reader behaves identically to before this feature."""
    records = [_make_record("sha1", "feat: feature"), _make_record("sha2", "fix: bug")]
    client = FakeCommitAnalysisClient()
    service = CommitAnalysisService(
        reader=FakeCommitReader(records),
        client=client,
        # No github_context_reader — backward compatible default.
    )
    results = service.analyze_commits("repo-1")
    assert len(results) == 2
    assert len(client.calls) == 2
    # No GITHUB CONTEXT in any prompt.
    for _system, messages in client.calls:
        user_msgs = [m for m in messages if m.role == "user"]
        assert user_msgs
        assert "GITHUB CONTEXT" not in user_msgs[0].content
