"""Tests for evidence_commit_shas, time_range, and confidence fields on pattern models."""

import pytest

from git_it.repository_ingestion.domain.patterns import (
    BugfixRecurrence,
    Hotspot,
    OwnershipConcentration,
    RefactorWave,
    RevertSignal,
    TestGrowthSignal,
)

# ---------------------------------------------------------------------------
# Hotspot
# ---------------------------------------------------------------------------


def test_hotspot_has_evidence_commit_shas_field() -> None:
    h = Hotspot(
        file_path="src/auth.py",
        commit_count=10,
        total_insertions=100,
        total_deletions=50,
        evidence_commit_shas=("abc1234", "def5678"),
    )
    assert h.evidence_commit_shas == ("abc1234", "def5678")


def test_hotspot_evidence_commit_shas_defaults_to_empty_tuple() -> None:
    h = Hotspot(file_path="x.py", commit_count=5, total_insertions=10, total_deletions=2)
    assert h.evidence_commit_shas == ()


def test_hotspot_confidence_scales_with_commit_count_low() -> None:
    h = Hotspot(
        file_path="x.py",
        commit_count=5,
        total_insertions=10,
        total_deletions=2,
        confidence=round(min(1.0, 5 / 20.0), 3),
    )
    assert h.confidence == pytest.approx(0.25)


def test_hotspot_confidence_scales_with_commit_count_high() -> None:
    h = Hotspot(
        file_path="x.py",
        commit_count=20,
        total_insertions=100,
        total_deletions=50,
        confidence=1.0,
    )
    assert h.confidence == pytest.approx(1.0)


def test_hotspot_confidence_caps_at_one() -> None:
    h = Hotspot(
        file_path="x.py",
        commit_count=100,
        total_insertions=1000,
        total_deletions=500,
        confidence=1.0,
    )
    assert h.confidence <= 1.0


def test_hotspot_confidence_defaults_to_zero() -> None:
    h = Hotspot(file_path="x.py", commit_count=5, total_insertions=10, total_deletions=2)
    assert h.confidence == 0.0


def test_hotspot_time_range_from_evidence() -> None:
    h = Hotspot(
        file_path="x.py",
        commit_count=5,
        total_insertions=10,
        total_deletions=2,
        time_range=("2024-01-15", "2026-06-01"),
    )
    assert h.time_range == ("2024-01-15", "2026-06-01")


def test_hotspot_time_range_defaults_to_none() -> None:
    h = Hotspot(file_path="x.py", commit_count=5, total_insertions=10, total_deletions=2)
    assert h.time_range is None


# ---------------------------------------------------------------------------
# BugfixRecurrence
# ---------------------------------------------------------------------------


def test_bugfix_recurrence_has_evidence_commit_shas_field() -> None:
    r = BugfixRecurrence(
        component="auth",
        bugfix_commit_count=3,
        evidence_commit_shas=("sha1", "sha2", "sha3"),
    )
    assert r.evidence_commit_shas == ("sha1", "sha2", "sha3")


def test_bugfix_recurrence_evidence_commit_shas_defaults_to_empty() -> None:
    r = BugfixRecurrence(component="auth", bugfix_commit_count=3)
    assert r.evidence_commit_shas == ()


def test_bugfix_recurrence_confidence_scales_with_count() -> None:
    r = BugfixRecurrence(
        component="auth",
        bugfix_commit_count=5,
        confidence=round(min(1.0, 5 / 10.0), 3),
    )
    assert r.confidence == pytest.approx(0.5)


def test_bugfix_recurrence_confidence_defaults_to_zero() -> None:
    r = BugfixRecurrence(component="auth", bugfix_commit_count=3)
    assert r.confidence == 0.0


def test_bugfix_recurrence_time_range_defaults_to_none() -> None:
    r = BugfixRecurrence(component="auth", bugfix_commit_count=3)
    assert r.time_range is None


# ---------------------------------------------------------------------------
# RefactorWave
# ---------------------------------------------------------------------------


def test_refactor_wave_confidence_from_ratio_half() -> None:
    rw = RefactorWave(
        commit_count=5,
        refactor_ratio=0.5,
        confidence=round(min(1.0, 0.5 * 2.0), 3),
    )
    assert rw.confidence == pytest.approx(1.0)


def test_refactor_wave_confidence_from_ratio_quarter() -> None:
    rw = RefactorWave(
        commit_count=5,
        refactor_ratio=0.25,
        confidence=round(min(1.0, 0.25 * 2.0), 3),
    )
    assert rw.confidence == pytest.approx(0.5)


def test_refactor_wave_confidence_defaults_to_zero() -> None:
    rw = RefactorWave(commit_count=5, refactor_ratio=0.3)
    assert rw.confidence == 0.0


def test_refactor_wave_evidence_commit_shas_defaults_to_empty() -> None:
    rw = RefactorWave(commit_count=5, refactor_ratio=0.3)
    assert rw.evidence_commit_shas == ()


def test_refactor_wave_time_range_defaults_to_none() -> None:
    rw = RefactorWave(commit_count=5, refactor_ratio=0.3)
    assert rw.time_range is None


# ---------------------------------------------------------------------------
# TestGrowthSignal
# ---------------------------------------------------------------------------


def test_test_growth_signal_confidence_from_ratio() -> None:
    tg = TestGrowthSignal(
        test_commit_count=4,
        bugfix_commit_count=2,
        test_to_bugfix_ratio=2.0,
        confidence=round(min(1.0, 2.0 / 2.0), 3),
    )
    assert tg.confidence == pytest.approx(1.0)


def test_test_growth_signal_confidence_defaults_to_zero() -> None:
    tg = TestGrowthSignal(test_commit_count=4, bugfix_commit_count=2, test_to_bugfix_ratio=2.0)
    assert tg.confidence == 0.0


def test_test_growth_signal_evidence_commit_shas_defaults_to_empty() -> None:
    tg = TestGrowthSignal(test_commit_count=4, bugfix_commit_count=2, test_to_bugfix_ratio=2.0)
    assert tg.evidence_commit_shas == ()


def test_test_growth_signal_time_range_defaults_to_none() -> None:
    tg = TestGrowthSignal(test_commit_count=4, bugfix_commit_count=2, test_to_bugfix_ratio=2.0)
    assert tg.time_range is None


# ---------------------------------------------------------------------------
# RevertSignal
# ---------------------------------------------------------------------------


def test_revert_signal_confidence_from_ratio() -> None:
    rs = RevertSignal(
        revert_count=2,
        revert_ratio=0.2,
        confidence=round(min(1.0, 0.2 * 5.0), 3),
    )
    assert rs.confidence == pytest.approx(1.0)


def test_revert_signal_confidence_defaults_to_zero() -> None:
    rs = RevertSignal(revert_count=2, revert_ratio=0.2)
    assert rs.confidence == 0.0


def test_revert_signal_evidence_commit_shas_defaults_to_empty() -> None:
    rs = RevertSignal(revert_count=2, revert_ratio=0.2)
    assert rs.evidence_commit_shas == ()


def test_revert_signal_time_range_defaults_to_none() -> None:
    rs = RevertSignal(revert_count=2, revert_ratio=0.2)
    assert rs.time_range is None


# ---------------------------------------------------------------------------
# OwnershipConcentration
# ---------------------------------------------------------------------------


def test_ownership_concentration_confidence_solo_author() -> None:
    oc = OwnershipConcentration(
        file_path="x.py",
        author_count=1,
        commit_count=10,
        confidence=round(1.0 - min(1.0, (1 - 1) / 5.0), 3),
    )
    assert oc.confidence == pytest.approx(1.0)


def test_ownership_concentration_confidence_many_authors() -> None:
    oc = OwnershipConcentration(
        file_path="x.py",
        author_count=6,
        commit_count=10,
        confidence=round(1.0 - min(1.0, (6 - 1) / 5.0), 3),
    )
    assert oc.confidence == pytest.approx(0.0)


def test_ownership_concentration_confidence_mid_range() -> None:
    oc = OwnershipConcentration(
        file_path="x.py",
        author_count=3,
        commit_count=10,
        confidence=round(1.0 - min(1.0, (3 - 1) / 5.0), 3),
    )
    assert oc.confidence == pytest.approx(0.6)


def test_ownership_concentration_confidence_defaults_to_zero() -> None:
    oc = OwnershipConcentration(file_path="x.py", author_count=2, commit_count=5)
    assert oc.confidence == 0.0


def test_ownership_concentration_evidence_commit_shas_defaults_to_empty() -> None:
    oc = OwnershipConcentration(file_path="x.py", author_count=2, commit_count=5)
    assert oc.evidence_commit_shas == ()


def test_ownership_concentration_time_range_defaults_to_none() -> None:
    oc = OwnershipConcentration(file_path="x.py", author_count=2, commit_count=5)
    assert oc.time_range is None
