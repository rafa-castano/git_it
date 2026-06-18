"""Tests that CommitAnalysisService forwards order/since/until to CommitReader."""

from git_it.repository_ingestion.application.commit_analysis_service import CommitAnalysisService
from git_it.repository_ingestion.application.commit_query_service import CommitRecord
from git_it.repository_ingestion.application.ports import LLMMessage
from git_it.repository_ingestion.domain.analysis import (
    CommitAnalysis,
    CommitCategory,
    RiskLevel,
)


class RecordingCommitReader:
    def __init__(self, records: list[CommitRecord] | None = None) -> None:
        self._records = records or []
        self.calls: list[dict] = []

    def list_commits_for_repository(
        self,
        repository_id: str,
        *,
        limit: int | None = None,
        order: str = "newest",
        since: str | None = None,
        until: str | None = None,
    ) -> list[CommitRecord]:
        self.calls.append({"limit": limit, "order": order, "since": since, "until": until})
        return self._records


class FakeAnalysisClient:
    def analyze_commit(self, system: str, messages: list[LLMMessage]) -> CommitAnalysis:
        return CommitAnalysis(
            commit_sha="dummy",
            summary="stub",
            category=CommitCategory.FEATURE,
            intent=None,
            intent_is_inferred=False,
            affected_components=[],
            risk_level=RiskLevel.LOW,
            confidence=0.9,
            evidence=[],
            limitations=[],
        )


def _make_service(reader: RecordingCommitReader) -> CommitAnalysisService:
    return CommitAnalysisService(reader=reader, client=FakeAnalysisClient())


def test_analyze_commits_passes_order_to_reader() -> None:
    reader = RecordingCommitReader()
    service = _make_service(reader)
    service.analyze_commits("repo-1", order="oldest")
    assert reader.calls[0]["order"] == "oldest"


def test_analyze_commits_passes_since_to_reader() -> None:
    reader = RecordingCommitReader()
    service = _make_service(reader)
    service.analyze_commits("repo-1", since="2024-01-01")
    assert reader.calls[0]["since"] == "2024-01-01"


def test_analyze_commits_passes_until_to_reader() -> None:
    reader = RecordingCommitReader()
    service = _make_service(reader)
    service.analyze_commits("repo-1", until="2024-12-31")
    assert reader.calls[0]["until"] == "2024-12-31"


def test_estimate_llm_calls_passes_order_to_reader() -> None:
    reader = RecordingCommitReader()
    service = _make_service(reader)
    service.estimate_llm_calls("repo-1", order="oldest")
    assert reader.calls[0]["order"] == "oldest"


def test_estimate_llm_calls_passes_since_to_reader() -> None:
    reader = RecordingCommitReader()
    service = _make_service(reader)
    service.estimate_llm_calls("repo-1", since="2024-06-01")
    assert reader.calls[0]["since"] == "2024-06-01"


def test_default_order_is_newest() -> None:
    reader = RecordingCommitReader()
    service = _make_service(reader)
    service.analyze_commits("repo-1")
    assert reader.calls[0]["order"] == "newest"
