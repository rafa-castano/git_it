"""Tests for LLM pattern synthesis layer (Batch 45)."""

from git_it.repository_ingestion.application.pattern_detection_service import (
    PatternDetectionService,
    _report_has_patterns,
)
from git_it.repository_ingestion.application.ports import FileChurnRecord
from git_it.repository_ingestion.domain.patterns import (
    BugfixRecurrence,
    Hotspot,
    PatternExplanation,
    PatternReport,
    RefactorWave,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeFileFactReader:
    def __init__(self, records: list[FileChurnRecord] | None = None) -> None:
        self._records = records or []

    def get_file_churn(self, repository_id: str) -> list[FileChurnRecord]:
        return self._records


class FakePatternSynthesisClient:
    """Records synthesize() calls and returns fixed explanations."""

    def __init__(self, explanations: list[PatternExplanation] | None = None) -> None:
        self._explanations = explanations or [
            PatternExplanation(
                pattern_type="hotspot",
                pattern_key="src/auth.py",
                why_it_matters="High churn indicates instability.",
                engineer_takeaway="Extract authentication logic.",
                confidence_note="",
            )
        ]
        self.calls: list[PatternReport] = []

    def synthesize(self, report: PatternReport) -> list[PatternExplanation]:
        self.calls.append(report)
        return self._explanations


def _hotspot_record(file_path: str = "src/auth.py", commit_count: int = 10) -> FileChurnRecord:
    return FileChurnRecord(
        file_path=file_path,
        commit_count=commit_count,
        total_insertions=50,
        total_deletions=20,
    )


def _report_with_hotspot() -> PatternReport:
    return PatternReport(
        repository_id="repo-1",
        hotspots=[
            Hotspot(
                file_path="src/auth.py",
                commit_count=12,
                total_insertions=100,
                total_deletions=40,
                confidence=0.6,
            )
        ],
    )


def _empty_report() -> PatternReport:
    return PatternReport(repository_id="repo-empty", hotspots=[])


# ---------------------------------------------------------------------------
# Tests: PatternDetectionService + synthesis client
# ---------------------------------------------------------------------------


def test_synthesis_called_when_client_present_and_patterns_exist() -> None:
    """When synthesis client is provided and report has patterns, synthesize() is called."""
    reader = FakeFileFactReader(records=[_hotspot_record(commit_count=10)])
    client = FakePatternSynthesisClient()
    service = PatternDetectionService(
        reader=reader,
        synthesis_client=client,
    )
    service.detect("repo-1", hotspot_threshold=5)
    assert len(client.calls) == 1


def test_synthesis_not_called_when_no_patterns() -> None:
    """When report has no patterns, synthesize() must NOT be called."""
    reader = FakeFileFactReader(records=[])  # no files → no hotspots
    client = FakePatternSynthesisClient()
    service = PatternDetectionService(
        reader=reader,
        synthesis_client=client,
    )
    service.detect("repo-empty", hotspot_threshold=5)
    assert len(client.calls) == 0


def test_synthesis_not_called_when_client_is_none() -> None:
    """No synthesis client → explanations list stays empty, no crash."""
    reader = FakeFileFactReader(records=[_hotspot_record(commit_count=10)])
    service = PatternDetectionService(reader=reader)  # no synthesis_client
    report = service.detect("repo-1", hotspot_threshold=5)
    assert report.explanations == []


def test_explanations_appear_in_report() -> None:
    """Explanations returned by the client are attached to the PatternReport."""
    reader = FakeFileFactReader(records=[_hotspot_record(commit_count=10)])
    expected = [
        PatternExplanation(
            pattern_type="hotspot",
            pattern_key="src/auth.py",
            why_it_matters="Important.",
            engineer_takeaway="Refactor it.",
            confidence_note="medium",
        )
    ]
    client = FakePatternSynthesisClient(explanations=expected)
    service = PatternDetectionService(
        reader=reader,
        synthesis_client=client,
    )
    report = service.detect("repo-1", hotspot_threshold=5)
    assert report.explanations == expected


# ---------------------------------------------------------------------------
# Tests: _report_has_patterns helper
# ---------------------------------------------------------------------------


def test_report_has_patterns_returns_true_for_hotspot() -> None:
    report = _report_with_hotspot()
    assert _report_has_patterns(report) is True


def test_report_has_patterns_returns_false_for_empty_report() -> None:
    report = _empty_report()
    assert _report_has_patterns(report) is False


def test_report_has_patterns_returns_true_for_bugfix_recurrence() -> None:
    report = PatternReport(
        repository_id="repo-1",
        hotspots=[],
        bugfix_recurrences=[BugfixRecurrence(component="auth", bugfix_commit_count=3)],
    )
    assert _report_has_patterns(report) is True


def test_report_has_patterns_returns_true_for_refactor_wave() -> None:
    report = PatternReport(
        repository_id="repo-1",
        hotspots=[],
        refactor_wave=RefactorWave(commit_count=5, refactor_ratio=0.3),
    )
    assert _report_has_patterns(report) is True


# ---------------------------------------------------------------------------
# Tests: InstructorPatternSynthesisAdapter builds correct user message
# ---------------------------------------------------------------------------


class FakeInstructor:
    """Captures the messages passed to create() so we can assert on them."""

    def __init__(self) -> None:
        self.captured_messages: list[dict] = []

    def synthesize(self, report: PatternReport) -> list[PatternExplanation]:
        from git_it.repository_ingestion.infrastructure.llm import (
            _build_pattern_synthesis_user_message,
        )

        msg = _build_pattern_synthesis_user_message(report)
        self.captured_messages.append({"content": msg})
        return []


def test_instructor_adapter_builds_correct_user_message() -> None:
    """User message must include hotspot file_path and commit_count inside [PATTERN DATA]."""
    report = PatternReport(
        repository_id="owner/repo",
        hotspots=[
            Hotspot(
                file_path="src/core/engine.py",
                commit_count=25,
                total_insertions=300,
                total_deletions=150,
                confidence=0.9,
            )
        ],
    )
    fake = FakeInstructor()
    fake.synthesize(report)
    msg = fake.captured_messages[0]["content"]
    assert "src/core/engine.py" in msg
    assert "25" in msg
    assert "[PATTERN DATA]" in msg
    assert "[/PATTERN DATA]" in msg
