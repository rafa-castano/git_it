"""Tests for the architectural shift detector (Batch 46)."""

from git_it.repository_ingestion.application.pattern_detection_service import (
    _compute_architectural_shifts,
)
from git_it.repository_ingestion.application.ports import FileChurnRecord
from git_it.repository_ingestion.domain.patterns import ArchitecturalShift


def _record(file_path: str, commit_count: int = 5) -> FileChurnRecord:
    return FileChurnRecord(
        file_path=file_path,
        commit_count=commit_count,
        total_insertions=10,
        total_deletions=2,
    )


def test_detects_top_level_directories_with_many_files() -> None:
    # Two top-level dirs so the structural signal fires; src/ has 6 files >= threshold of 5
    records = [_record(f"src/module_{i}/file.py") for i in range(6)] + [
        _record("tests/test_main.py"),
    ]
    result = _compute_architectural_shifts(records, date_map={}, file_evidence={})
    shift_types = [s.shift_type for s in result]
    assert "new_top_level_dir" in shift_types
    shift = next(s for s in result if s.shift_type == "new_top_level_dir")
    assert "src" in shift.description


def test_skips_dirs_with_few_files() -> None:
    records = [_record(f"tiny/file_{i}.py") for i in range(3)]
    result = _compute_architectural_shifts(records, date_map={}, file_evidence={})
    new_dir_shifts = [s for s in result if s.shift_type == "new_top_level_dir"]
    assert new_dir_shifts == []


def test_single_top_level_dir_not_reported() -> None:
    records = [_record(f"src/module_{i}/file.py") for i in range(10)]
    result = _compute_architectural_shifts(records, date_map={}, file_evidence={})
    # Only 1 top-level dir → no structural signal
    assert result == []


def test_module_extraction_detected_when_multiple_large_dirs() -> None:
    records = (
        [_record(f"src/mod_{i}/file.py") for i in range(40)]
        + [_record(f"tests/test_{i}.py") for i in range(15)]
        + [_record(f"services/svc_{i}.py") for i in range(10)]
    )
    result = _compute_architectural_shifts(records, date_map={}, file_evidence={})
    shift_types = [s.shift_type for s in result]
    assert "module_extraction" in shift_types


def test_confidence_scales_with_file_count_for_new_top_level_dir() -> None:
    # 5 files → confidence = 5/20 = 0.25
    records_5 = [_record(f"src/file_{i}.py") for i in range(5)] + [
        _record(f"lib/file_{i}.py") for i in range(5)
    ]
    result_5 = _compute_architectural_shifts(records_5, date_map={}, file_evidence={})
    new_dir_shifts = [s for s in result_5 if s.shift_type == "new_top_level_dir"]
    assert len(new_dir_shifts) > 0
    for shift in new_dir_shifts:
        assert abs(shift.confidence - 0.25) < 1e-9

    # 20+ files → confidence = 1.0
    records_20 = [_record(f"src/file_{i}.py") for i in range(20)] + [
        _record(f"lib/file_{i}.py") for i in range(20)
    ]
    result_20 = _compute_architectural_shifts(records_20, date_map={}, file_evidence={})
    new_dir_shifts_20 = [s for s in result_20 if s.shift_type == "new_top_level_dir"]
    assert len(new_dir_shifts_20) > 0
    for shift in new_dir_shifts_20:
        assert shift.confidence == 1.0


def test_architectural_shift_dataclass_fields() -> None:
    s = ArchitecturalShift(
        shift_type="new_top_level_dir",
        description="Directory 'services/' contains 47 tracked files",
        evidence_commit_shas=("abc1234",),
        time_range=("2024-01-01", "2024-06-01"),
        confidence=0.8,
    )
    assert s.shift_type == "new_top_level_dir"
    assert s.description == "Directory 'services/' contains 47 tracked files"
    assert s.confidence == 0.8
