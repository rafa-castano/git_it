"""Tests for the security advisories domain model (spec 026) — SecurityAdvisory +
AdvisoryEvidence.

SecurityAdvisory is the raw, ephemeral, never-persisted LLM-input shape (GitHub
security advisory metadata, including raw description text). AdvisoryEvidence is
the schema-validated, persisted, narrative-facing LLM output — this is where the
evidence-link requirement (an advisory_url matching the GitHub security
advisories URL pattern) and the severity enum are deterministically enforced.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from git_it.repository_ingestion.domain.advisories import AdvisoryEvidence, SecurityAdvisory


def _valid_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "ghsa_id": "GHSA-pmv8-rq9r-6j72",
        "advisory_url": "https://github.com/owner/repo/security/advisories/GHSA-pmv8-rq9r-6j72",
        "severity": "high",
        "summary": "A SQL injection vulnerability was found and fixed in the query builder.",
        "confidence": 0.8,
        "limitations": [],
        "source_inputs": ["GHSA-pmv8-rq9r-6j72"],
        "generated_at": datetime(2026, 1, 1, tzinfo=UTC),
        "model": "test-model",
    }
    kwargs.update(overrides)
    return kwargs


def test_advisory_evidence_constructs_with_valid_advisory_url() -> None:
    evidence = AdvisoryEvidence(**_valid_kwargs())
    assert evidence.advisory_url == (
        "https://github.com/owner/repo/security/advisories/GHSA-pmv8-rq9r-6j72"
    )
    assert evidence.severity == "high"


def test_advisory_evidence_rejects_missing_advisory_url() -> None:
    kwargs = _valid_kwargs()
    del kwargs["advisory_url"]
    with pytest.raises(ValidationError):
        AdvisoryEvidence(**kwargs)


def test_advisory_evidence_rejects_empty_advisory_url() -> None:
    with pytest.raises(ValidationError):
        AdvisoryEvidence(**_valid_kwargs(advisory_url=""))


def test_advisory_evidence_rejects_non_github_url() -> None:
    with pytest.raises(ValidationError):
        AdvisoryEvidence(
            **_valid_kwargs(
                advisory_url="https://evil.com/owner/repo/security/advisories/GHSA-pmv8-rq9r-6j72"
            )
        )


def test_advisory_evidence_rejects_url_not_matching_advisories_pattern() -> None:
    with pytest.raises(ValidationError):
        AdvisoryEvidence(
            **_valid_kwargs(advisory_url="https://github.com/owner/repo/discussions/1")
        )


def test_advisory_evidence_rejects_confidence_above_one() -> None:
    with pytest.raises(ValidationError):
        AdvisoryEvidence(**_valid_kwargs(confidence=1.5))


def test_advisory_evidence_rejects_confidence_below_zero() -> None:
    with pytest.raises(ValidationError):
        AdvisoryEvidence(**_valid_kwargs(confidence=-0.1))


def test_advisory_evidence_rejects_invalid_severity() -> None:
    with pytest.raises(ValidationError):
        AdvisoryEvidence(**_valid_kwargs(severity="extreme"))


def test_advisory_evidence_defaults_limitations_to_empty_list() -> None:
    kwargs = _valid_kwargs()
    del kwargs["limitations"]
    evidence = AdvisoryEvidence(**kwargs)
    assert evidence.limitations == []


def test_security_advisory_holds_raw_fields_never_validated() -> None:
    advisory = SecurityAdvisory(
        ghsa_id="GHSA-pmv8-rq9r-6j72",
        cve_id="CVE-2026-12345",
        summary="SQL injection in query builder",
        description="Raw untrusted advisory description text.",
        severity="high",
        html_url="https://github.com/owner/repo/security/advisories/GHSA-pmv8-rq9r-6j72",
        published_at="2026-01-01T00:00:00Z",
    )
    assert advisory.ghsa_id == "GHSA-pmv8-rq9r-6j72"
    assert advisory.cve_id == "CVE-2026-12345"
    assert advisory.severity == "high"
