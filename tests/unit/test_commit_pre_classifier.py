"""Tests for CommitPreClassifier — skip / include / sample decision logic."""

from git_it.repository_ingestion.application.commit_query_service import CommitRecord
from git_it.repository_ingestion.application.pre_classifier import (
    CommitPreClassifier,
)
from git_it.repository_ingestion.domain.analysis import CommitCategory


def _commit(
    message: str = "Add feature",
    parent_shas: tuple[str, ...] = ("abc",),
) -> CommitRecord:
    return CommitRecord(
        repository_id="repo-1",
        sha="abc1234",
        committed_at="2026-01-01T00:00:00+00:00",
        message=message,
        author_name="Alice",
        committer_name="Alice",
        parent_shas=parent_shas,
    )


_classifier = CommitPreClassifier()


# ---------------------------------------------------------------------------
# Skip tests
# ---------------------------------------------------------------------------


def test_dependabot_bump_is_skipped() -> None:
    result = _classifier.classify(_commit("Bump lodash from 4.17.20 to 4.17.21"))
    assert result.decision == "skip"


def test_conventional_deps_is_skipped() -> None:
    result = _classifier.classify(_commit("chore(deps): bump react to 18.0"))
    assert result.decision == "skip"


def test_snyk_bot_is_skipped() -> None:
    result = _classifier.classify(_commit("[Snyk] Upgrade axios from 0.21.1 to 0.21.4"))
    assert result.decision == "skip"


def test_renovate_is_skipped() -> None:
    result = _classifier.classify(_commit("renovate: update dependency eslint to v8"))
    assert result.decision == "skip"


def test_merge_pr_message_is_skipped() -> None:
    result = _classifier.classify(_commit("Merge pull request #123 from org/feature"))
    assert result.decision == "skip"


def test_merge_branch_message_is_skipped() -> None:
    result = _classifier.classify(_commit("Merge branch 'feature/auth' into main"))
    assert result.decision == "skip"


def test_merge_commit_by_parent_count_is_skipped() -> None:
    result = _classifier.classify(_commit("Merge something", parent_shas=("abc", "def")))
    assert result.decision == "skip"


def test_lock_file_update_is_skipped() -> None:
    result = _classifier.classify(_commit("Update go.sum"))
    assert result.decision == "skip"


def test_format_only_is_skipped() -> None:
    result = _classifier.classify(_commit("Apply black formatting"))
    assert result.decision == "skip"


def test_release_commit_is_skipped() -> None:
    result = _classifier.classify(_commit("chore: release v1.2.3"))
    assert result.decision == "skip"


def test_changelog_is_skipped() -> None:
    result = _classifier.classify(_commit("Update CHANGELOG"))
    assert result.decision == "skip"


def test_ci_commit_is_skipped() -> None:
    result = _classifier.classify(_commit("ci: update workflow"))
    assert result.decision == "skip"


def test_skip_sets_build_category() -> None:
    result = _classifier.classify(_commit("Bump lodash from 4.17.20 to 4.17.21"))
    assert result.auto_category == CommitCategory.BUILD


def test_skip_reason_is_non_empty() -> None:
    result = _classifier.classify(_commit("Bump lodash from 4.17.20 to 4.17.21"))
    assert result.reason != ""


# ---------------------------------------------------------------------------
# Include tests
# ---------------------------------------------------------------------------


def test_feat_commit_is_included() -> None:
    result = _classifier.classify(_commit("feat: add user authentication"))
    assert result.decision == "include"


def test_feat_scoped_commit_is_included() -> None:
    result = _classifier.classify(_commit("feat(api): add rate limiting"))
    assert result.decision == "include"


def test_fix_commit_is_included() -> None:
    result = _classifier.classify(_commit("fix: resolve null pointer in auth service"))
    assert result.decision == "include"


def test_fix_typo_is_not_included() -> None:
    result = _classifier.classify(_commit("fix: typo in comment"))
    assert result.decision != "include"


def test_refactor_commit_is_included() -> None:
    result = _classifier.classify(_commit("refactor: extract service layer"))
    assert result.decision == "include"


def test_perf_commit_is_included() -> None:
    result = _classifier.classify(_commit("perf: optimize database query"))
    assert result.decision == "include"


def test_revert_commit_is_included() -> None:
    result = _classifier.classify(_commit("revert: feat(auth): add token refresh"))
    assert result.decision == "include"


def test_breaking_scope_is_included() -> None:
    result = _classifier.classify(_commit("feat(auth)!: redesign token flow"))
    assert result.decision == "include"


def test_breaking_change_in_body_is_included() -> None:
    msg = "feat: update API\n\nBREAKING CHANGE: remove deprecated API"
    result = _classifier.classify(_commit(msg))
    assert result.decision == "include"


def test_security_keyword_is_included() -> None:
    result = _classifier.classify(_commit("Patch vulnerability in JWT handling"))
    assert result.decision == "include"


def test_auth_keyword_is_included() -> None:
    result = _classifier.classify(_commit("Add OAuth2 support for third-party login"))
    assert result.decision == "include"


def test_migration_keyword_is_included() -> None:
    result = _classifier.classify(_commit("Add database migration for user roles"))
    assert result.decision == "include"


def test_hotfix_keyword_is_included() -> None:
    result = _classifier.classify(_commit("hotfix: resolve auth bypass"))
    assert result.decision == "include"


def test_include_reason_is_non_empty() -> None:
    result = _classifier.classify(_commit("feat: add user authentication"))
    assert result.reason != ""


# ---------------------------------------------------------------------------
# Sample tests
# ---------------------------------------------------------------------------


def test_regular_commit_is_sample() -> None:
    result = _classifier.classify(_commit("Add logging to request handler"))
    assert result.decision == "sample"


def test_generic_chore_is_sample() -> None:
    result = _classifier.classify(_commit("chore: update .gitignore"))
    assert result.decision == "sample"


def test_docs_update_is_sample() -> None:
    result = _classifier.classify(_commit("docs: update README"))
    assert result.decision == "sample"
