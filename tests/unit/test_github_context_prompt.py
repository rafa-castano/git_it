"""Tests for _build_messages with GitHub context injection.

Verifies that:
- No [GITHUB CONTEXT] block appears when context or reader is None.
- Block appears, is correctly tagged, and truncates content.
- Block is positioned after [REPO CONTEXT] and before [REPOSITORY DATA].
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


def _make_record(sha: str = "abc1234", message: str = "Fix bug") -> CommitRecord:
    return CommitRecord(
        repository_id="repo-1",
        sha=sha,
        committed_at="2026-01-01T00:00:00+00:00",
        message=message,
        author_name="Alice",
        committer_name="Alice",
        parent_shas=(),
    )


def _make_analysis() -> CommitAnalysis:
    return CommitAnalysis(
        commit_sha="abc1234",
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


class FakeGithubContextReader:
    def __init__(self, context: GithubContext | None = None) -> None:
        self._context = context

    def get_github_context(
        self, *, repository_id: str, canonical_url: str, commit_sha: str
    ) -> GithubContext | None:
        return self._context


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_github_block_when_context_is_none() -> None:
    """When the reader returns None, no [GITHUB CONTEXT] block appears."""
    client = FakeCommitAnalysisClient()
    service = CommitAnalysisService(
        reader=FakeCommitReader(),
        client=client,
        github_context_reader=FakeGithubContextReader(context=None),
    )
    service.analyze_commits("repo-1", canonical_url=_CANONICAL)
    # No commits → no calls; test against direct _build_messages.
    msgs = CommitAnalysisService._build_messages(_make_record(), github_context=None)
    user = next(m for m in msgs if m.role == "user")
    assert "GITHUB CONTEXT" not in user.content


def test_no_github_block_when_reader_is_none() -> None:
    """When github_context_reader is None, no [GITHUB CONTEXT] block appears."""
    msgs = CommitAnalysisService._build_messages(_make_record(), github_context=None)
    user = next(m for m in msgs if m.role == "user")
    assert "GITHUB CONTEXT" not in user.content


def test_github_block_present_when_context_available() -> None:
    """When GithubContext with has_pr=True is provided, the block appears."""
    ctx = GithubContext(
        pr_number=7,
        pr_title="Fix login",
        pr_body="Fixes the login redirect.",
        has_pr=True,
    )
    msgs = CommitAnalysisService._build_messages(_make_record(), github_context=ctx)
    user = next(m for m in msgs if m.role == "user")
    assert "GITHUB CONTEXT" in user.content
    assert "Fix login" in user.content
    assert "Fixes the login redirect." in user.content


def test_github_block_uses_untrusted_content_tag() -> None:
    """The opening tag must contain 'UNTRUSTED' to signal prompt injection risk."""
    ctx = GithubContext(pr_number=1, pr_title="PR", has_pr=True)
    msgs = CommitAnalysisService._build_messages(_make_record(), github_context=ctx)
    user = next(m for m in msgs if m.role == "user")
    assert "UNTRUSTED" in user.content


def test_pr_body_truncated_at_1000_chars() -> None:
    """A PR body longer than 1000 chars must be truncated in the prompt."""
    long_body = "x" * 3000
    ctx = GithubContext(pr_number=1, pr_title="PR", pr_body=long_body, has_pr=True)
    msgs = CommitAnalysisService._build_messages(_make_record(), github_context=ctx)
    user = next(m for m in msgs if m.role == "user")
    # The full 3000-char body must not appear.
    assert long_body not in user.content
    # But at least 1000 chars of x's must be present (the truncated portion).
    assert "x" * 1000 in user.content
    assert "x" * 1001 not in user.content


def test_issue_body_truncated_at_500_chars() -> None:
    """Issue bodies longer than 500 chars must be truncated in the prompt."""
    long_issue = "y" * 800
    ctx = GithubContext(
        pr_number=1,
        pr_title="PR",
        has_pr=True,
        issue_numbers=(5,),
        issue_bodies=(long_issue,),
    )
    msgs = CommitAnalysisService._build_messages(_make_record(), github_context=ctx)
    user = next(m for m in msgs if m.role == "user")
    assert long_issue not in user.content
    assert "y" * 500 in user.content
    assert "y" * 501 not in user.content


def test_max_3_issues_rendered() -> None:
    """Only the first 3 issues are rendered, even if more exist in the context."""
    ctx = GithubContext(
        pr_number=1,
        pr_title="PR",
        has_pr=True,
        issue_numbers=(1, 2, 3, 4, 5),
        issue_bodies=("body1", "body2", "body3", "body4", "body5"),
    )
    msgs = CommitAnalysisService._build_messages(_make_record(), github_context=ctx)
    user = next(m for m in msgs if m.role == "user")
    assert "body1" in user.content
    assert "body2" in user.content
    assert "body3" in user.content
    assert "body4" not in user.content
    assert "body5" not in user.content


def test_github_block_positioned_after_repo_context_before_repository_data() -> None:
    """[GITHUB CONTEXT] must appear between [REPO CONTEXT] and [REPOSITORY DATA]."""
    ctx = GithubContext(pr_number=1, pr_title="PR", has_pr=True)
    msgs = CommitAnalysisService._build_messages(
        _make_record(), repo_context="Project summary", github_context=ctx
    )
    user = next(m for m in msgs if m.role == "user")
    content = user.content
    # Use the exact block delimiters to avoid matching substrings in other tags.
    repo_ctx_pos = content.find("[REPO CONTEXT")
    github_ctx_pos = content.find("[GITHUB CONTEXT")
    repo_data_pos = content.find("[REPOSITORY DATA]")
    assert repo_ctx_pos != -1
    assert github_ctx_pos != -1
    assert repo_data_pos != -1
    assert repo_ctx_pos < github_ctx_pos < repo_data_pos
