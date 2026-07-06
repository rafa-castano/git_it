"""Tests for the releases domain model (spec 026) — Release + ReleaseEvidence.

Release is the raw, ephemeral, never-persisted LLM-input shape (GitHub release
metadata, including raw release-notes markdown). ReleaseEvidence is the
schema-validated, persisted, narrative-facing LLM output — this is where the
evidence-link requirement (a release_url matching the GitHub releases/tag URL
pattern) is deterministically enforced.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from git_it.repository_ingestion.domain.releases import Release, ReleaseEvidence


def _valid_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "tag_name": "v1.2.3",
        "release_url": "https://github.com/owner/repo/releases/tag/v1.2.3",
        "claim_type": "feature_release",
        "summary": "Adds a new caching layer and improves startup time.",
        "confidence": 0.8,
        "limitations": [],
        "source_inputs": ["v1.2.3"],
        "generated_at": datetime(2026, 1, 1, tzinfo=UTC),
        "model": "test-model",
    }
    kwargs.update(overrides)
    return kwargs


def test_release_evidence_constructs_with_valid_release_url() -> None:
    evidence = ReleaseEvidence(**_valid_kwargs())
    assert evidence.release_url == "https://github.com/owner/repo/releases/tag/v1.2.3"
    assert evidence.claim_type == "feature_release"


def test_release_evidence_rejects_missing_release_url() -> None:
    kwargs = _valid_kwargs()
    del kwargs["release_url"]
    with pytest.raises(ValidationError):
        ReleaseEvidence(**kwargs)


def test_release_evidence_rejects_empty_release_url() -> None:
    with pytest.raises(ValidationError):
        ReleaseEvidence(**_valid_kwargs(release_url=""))


def test_release_evidence_rejects_non_github_url() -> None:
    with pytest.raises(ValidationError):
        ReleaseEvidence(
            **_valid_kwargs(release_url="https://evil.com/owner/repo/releases/tag/v1.2.3")
        )


def test_release_evidence_rejects_url_not_matching_releases_pattern() -> None:
    with pytest.raises(ValidationError):
        ReleaseEvidence(**_valid_kwargs(release_url="https://github.com/owner/repo/discussions/1"))


def test_release_evidence_rejects_confidence_above_one() -> None:
    with pytest.raises(ValidationError):
        ReleaseEvidence(**_valid_kwargs(confidence=1.5))


def test_release_evidence_rejects_confidence_below_zero() -> None:
    with pytest.raises(ValidationError):
        ReleaseEvidence(**_valid_kwargs(confidence=-0.1))


def test_release_evidence_rejects_invalid_claim_type() -> None:
    with pytest.raises(ValidationError):
        ReleaseEvidence(**_valid_kwargs(claim_type="something_else"))


def test_release_evidence_defaults_limitations_to_empty_list() -> None:
    kwargs = _valid_kwargs()
    del kwargs["limitations"]
    evidence = ReleaseEvidence(**kwargs)
    assert evidence.limitations == []


def test_release_holds_raw_fields_never_validated() -> None:
    release = Release(
        tag_name="v1.2.3",
        name="Version 1.2.3",
        body="Raw untrusted release notes text.",
        html_url="https://github.com/owner/repo/releases/tag/v1.2.3",
        published_at="2026-01-01T00:00:00Z",
        prerelease=False,
    )
    assert release.tag_name == "v1.2.3"
    assert release.name == "Version 1.2.3"
    assert release.prerelease is False
