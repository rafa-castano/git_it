"""Tests for the project-doc domain model (spec 025) — ProjectDocContent.

ProjectDocContent is a plain frozen dataclass (not Pydantic) — an internal,
backend-agnostic persistence shape for a captured README/CHANGELOG excerpt,
not an LLM-output-validation boundary like DiscussionEvidence/CommitAnalysis.
"""

from datetime import UTC, datetime

from git_it.repository_ingestion.domain.project_docs import ProjectDocContent


def test_project_doc_content_constructs_with_both_readme_and_changelog() -> None:
    content = ProjectDocContent(
        repository_id="repo-1",
        readme_text="# My Project\n\nThis project does X.",
        readme_truncated=False,
        changelog_text="## 1.0.0\n\n- Initial release",
        changelog_truncated=False,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert content.repository_id == "repo-1"
    assert content.readme_text == "# My Project\n\nThis project does X."
    assert content.readme_truncated is False
    assert content.changelog_text == "## 1.0.0\n\n- Initial release"
    assert content.changelog_truncated is False
    assert content.captured_at == datetime(2026, 1, 1, tzinfo=UTC)


def test_project_doc_content_constructs_with_readme_only() -> None:
    content = ProjectDocContent(
        repository_id="repo-2",
        readme_text="# Only a README",
        readme_truncated=False,
        changelog_text=None,
        changelog_truncated=False,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert content.readme_text == "# Only a README"
    assert content.changelog_text is None
    assert content.changelog_truncated is False


def test_project_doc_content_constructs_with_changelog_only() -> None:
    content = ProjectDocContent(
        repository_id="repo-3",
        readme_text=None,
        readme_truncated=False,
        changelog_text="## Unreleased\n\n- Work in progress",
        changelog_truncated=False,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert content.readme_text is None
    assert content.changelog_text == "## Unreleased\n\n- Work in progress"


def test_project_doc_content_records_truncation_flags() -> None:
    content = ProjectDocContent(
        repository_id="repo-4",
        readme_text="x" * 2000,
        readme_truncated=True,
        changelog_text="y" * 2000,
        changelog_truncated=True,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert content.readme_truncated is True
    assert content.changelog_truncated is True
