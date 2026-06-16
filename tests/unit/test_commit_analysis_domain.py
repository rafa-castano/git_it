import pytest
from pydantic import ValidationError

from git_it.repository_ingestion.domain.analysis import (
    CommitAnalysis,
    CommitCategory,
    EvidenceRef,
    RiskLevel,
)


def _valid_analysis(**overrides: object) -> CommitAnalysis:
    defaults: dict[str, object] = dict(
        commit_sha="abc1234",
        summary="Added login page",
        category=CommitCategory.FEATURE,
        intent="Implement user authentication",
        intent_is_inferred=False,
        affected_components=["auth"],
        risk_level=RiskLevel.LOW,
        confidence=0.85,
        evidence=[],
        limitations=[],
    )
    return CommitAnalysis(**{**defaults, **overrides})


def test_commit_analysis_has_all_spec_fields() -> None:
    analysis = _valid_analysis()
    assert analysis.commit_sha == "abc1234"
    assert analysis.summary == "Added login page"
    assert analysis.category == CommitCategory.FEATURE
    assert analysis.intent == "Implement user authentication"
    assert analysis.intent_is_inferred is False
    assert analysis.affected_components == ["auth"]
    assert analysis.risk_level == RiskLevel.LOW
    assert analysis.confidence == 0.85
    assert analysis.evidence == []
    assert analysis.limitations == []


def test_commit_category_covers_all_spec_values() -> None:
    expected = {
        "feature",
        "bugfix",
        "refactor",
        "test",
        "docs",
        "build",
        "security",
        "performance",
        "chore",
        "unknown",
    }
    assert {c.value for c in CommitCategory} == expected


def test_risk_level_covers_all_spec_values() -> None:
    assert {r.value for r in RiskLevel} == {"low", "medium", "high", "unknown"}


def test_confidence_above_1_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _valid_analysis(confidence=1.01)


def test_confidence_below_0_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _valid_analysis(confidence=-0.01)


def test_intent_can_be_none() -> None:
    analysis = _valid_analysis(intent=None, intent_is_inferred=True)
    assert analysis.intent is None
    assert analysis.intent_is_inferred is True


def test_evidence_ref_optional_fields_default_to_none() -> None:
    ref = EvidenceRef(commit_sha="abc1234")
    assert ref.file_path is None
    assert ref.quote is None
