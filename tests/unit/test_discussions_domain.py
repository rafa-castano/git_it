"""Tests for the discussions domain model (spec 022) — Discussion + DiscussionEvidence.

Discussion is the raw, ephemeral, never-persisted LLM-input shape. DiscussionEvidence is
the schema-validated, persisted, narrative-facing LLM output — this is where the
evidence-link requirement (a discussion_url matching the GitHub discussions URL pattern)
is deterministically enforced.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from git_it.repository_ingestion.domain.discussions import Discussion, DiscussionEvidence


def _valid_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "discussion_id": "123",
        "discussion_url": "https://github.com/owner/repo/discussions/123",
        "claim_type": "design_rationale",
        "summary": "The team chose approach X over Y because of a performance constraint.",
        "confidence": 0.8,
        "limitations": [],
        "source_inputs": ["123"],
        "generated_at": datetime(2026, 1, 1, tzinfo=UTC),
        "model": "test-model",
    }
    kwargs.update(overrides)
    return kwargs


def test_discussion_evidence_constructs_with_valid_discussion_url() -> None:
    evidence = DiscussionEvidence(**_valid_kwargs())
    assert evidence.discussion_url == "https://github.com/owner/repo/discussions/123"
    assert evidence.claim_type == "design_rationale"


def test_discussion_evidence_rejects_missing_discussion_url() -> None:
    kwargs = _valid_kwargs()
    del kwargs["discussion_url"]
    with pytest.raises(ValidationError):
        DiscussionEvidence(**kwargs)


def test_discussion_evidence_rejects_empty_discussion_url() -> None:
    with pytest.raises(ValidationError):
        DiscussionEvidence(**_valid_kwargs(discussion_url=""))


def test_discussion_evidence_rejects_non_github_url() -> None:
    with pytest.raises(ValidationError):
        DiscussionEvidence(
            **_valid_kwargs(discussion_url="https://example.com/owner/repo/discussions/123")
        )


def test_discussion_evidence_rejects_url_not_matching_discussions_pattern() -> None:
    with pytest.raises(ValidationError):
        DiscussionEvidence(
            **_valid_kwargs(discussion_url="https://github.com/owner/repo/issues/123")
        )


def test_discussion_evidence_rejects_url_with_non_numeric_discussion_number() -> None:
    with pytest.raises(ValidationError):
        DiscussionEvidence(
            **_valid_kwargs(discussion_url="https://github.com/owner/repo/discussions/abc")
        )


def test_discussion_evidence_rejects_confidence_above_one() -> None:
    with pytest.raises(ValidationError):
        DiscussionEvidence(**_valid_kwargs(confidence=1.5))


def test_discussion_evidence_rejects_confidence_below_zero() -> None:
    with pytest.raises(ValidationError):
        DiscussionEvidence(**_valid_kwargs(confidence=-0.1))


def test_discussion_evidence_rejects_invalid_claim_type() -> None:
    with pytest.raises(ValidationError):
        DiscussionEvidence(**_valid_kwargs(claim_type="something_else"))


def test_discussion_evidence_defaults_limitations_to_empty_list() -> None:
    kwargs = _valid_kwargs()
    del kwargs["limitations"]
    evidence = DiscussionEvidence(**kwargs)
    assert evidence.limitations == []


def test_discussion_holds_raw_fields_never_validated() -> None:
    discussion = Discussion(
        id="123",
        url="https://github.com/owner/repo/discussions/123",
        title="Why did we choose X?",
        body="Raw untrusted discussion body text.",
        answer_body=None,
        category="Q&A",
        is_answered=True,
        upvote_count=1,
        reaction_count=2,
        comment_count=3,
        updated_at="2026-01-01T00:00:00Z",
    )
    assert discussion.id == "123"
    assert discussion.title == "Why did we choose X?"
    assert discussion.answer_body is None
