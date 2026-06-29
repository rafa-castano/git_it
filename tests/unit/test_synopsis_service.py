"""Tests for case study synopsis extraction, storage, and incremental use."""

from git_it.repository_ingestion.application.narrative_service import NarrativeService
from git_it.repository_ingestion.application.ports import (
    CaseStudyRecord,
    LLMMessage,
    TimestampedAnalysis,
)
from git_it.repository_ingestion.domain.analysis import CommitAnalysis, CommitCategory, RiskLevel
from git_it.repository_ingestion.domain.patterns import PatternReport


def _analysis(sha: str = "abc1234") -> CommitAnalysis:
    return CommitAnalysis(
        commit_sha=sha,
        summary="summary",
        category=CommitCategory.FEATURE,
        confidence=0.9,
        risk_level=RiskLevel.LOW,
        intent=None,
        intent_is_inferred=False,
        affected_components=[],
        evidence=[],
        limitations=[],
    )


class FakeTemporalReader:
    def __init__(self, items: list[TimestampedAnalysis] | None = None) -> None:
        self._items = items or [
            TimestampedAnalysis(analysis=_analysis(), committed_at="2024-01-01T00:00:00")
        ]

    def list_analyses_with_dates(self, repository_id: str) -> list[TimestampedAnalysis]:
        return list(self._items)

    def list_analyses_since(self, repository_id: str, *, since: str) -> list[TimestampedAnalysis]:
        return [i for i in self._items if i.committed_at >= since]


class FakePatternService:
    def detect(self, repository_id: str, *, hotspot_threshold: int = 5) -> PatternReport:
        return PatternReport(repository_id=repository_id, hotspots=[])


class FakeLLMClient:
    """Returns a narrative that includes a ## Synopsis section at the end."""

    def __init__(self, with_synopsis: bool = True) -> None:
        self.call_count = 0
        self.last_messages: list[LLMMessage] = []
        self._with_synopsis = with_synopsis

    def complete(self, messages: list[LLMMessage]) -> str:
        self.call_count += 1
        self.last_messages = list(messages)
        if self._with_synopsis:
            return "## Overview\nCase study content.\n\n## Synopsis\nKey patterns: TDD adoption."
        return "## Overview\nCase study content."


class FakeCaseStudyStore:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], CaseStudyRecord] = {}

    def save_case_study(self, record: CaseStudyRecord) -> None:
        self._store[(record.repository_id, record.audience)] = record

    def get_case_study(
        self, repository_id: str, audience: str = "beginner"
    ) -> CaseStudyRecord | None:
        return self._store.get((repository_id, audience))


class FakeSynopsisStore:
    def __init__(self, existing: str | None = None) -> None:
        self._store: dict[str, str] = {}
        if existing is not None:
            self._store["repo-1"] = existing

    def save_synopsis(self, repository_id: str, synopsis: str) -> None:
        self._store[repository_id] = synopsis

    def get_synopsis(self, repository_id: str) -> str | None:
        return self._store.get(repository_id)


def _service(
    llm: FakeLLMClient,
    case_study_store: FakeCaseStudyStore | None = None,
    synopsis_store: FakeSynopsisStore | None = None,
    items: list[TimestampedAnalysis] | None = None,
) -> NarrativeService:
    return NarrativeService(
        temporal_reader=FakeTemporalReader(items),
        pattern_service=FakePatternService(),
        llm_client=llm,
        case_study_store=case_study_store,
        synopsis_store=synopsis_store,
    )


# ---------------------------------------------------------------------------
# Full generation — synopsis extraction and storage
# ---------------------------------------------------------------------------


def test_synopsis_stripped_from_stored_narrative() -> None:
    llm = FakeLLMClient(with_synopsis=True)
    store = FakeCaseStudyStore()
    synopsis_store = FakeSynopsisStore()
    _service(llm, store, synopsis_store).generate("repo-1")
    saved = store.get_case_study("repo-1")
    assert saved is not None
    assert "## Synopsis" not in saved.narrative


def test_synopsis_saved_to_synopsis_store() -> None:
    llm = FakeLLMClient(with_synopsis=True)
    synopsis_store = FakeSynopsisStore()
    _service(llm, synopsis_store=synopsis_store).generate("repo-1")
    result = synopsis_store.get_synopsis("repo-1")
    assert result == "Key patterns: TDD adoption."


def test_no_synopsis_in_llm_output_does_not_break() -> None:
    llm = FakeLLMClient(with_synopsis=False)
    store = FakeCaseStudyStore()
    synopsis_store = FakeSynopsisStore()
    result = _service(llm, store, synopsis_store).generate("repo-1")
    assert result.narrative != ""
    assert synopsis_store.get_synopsis("repo-1") is None


# ---------------------------------------------------------------------------
# Incremental generation — synopsis used as context
# ---------------------------------------------------------------------------


def test_incremental_uses_synopsis_not_full_narrative() -> None:
    """When synopsis is available, it appears in the incremental user message."""
    synopsis_text = "Prior summary: hexagonal arch, TDD."
    existing = CaseStudyRecord(
        repository_id="repo-1",
        narrative="## Overview\nVery long original narrative.",
        commit_count=1,
        hotspot_count=0,
        generated_at="2024-01-01T00:00:00",
        audience="beginner",
    )
    case_store = FakeCaseStudyStore()
    case_store.save_case_study(existing)
    synopsis_store = FakeSynopsisStore(existing=synopsis_text)
    llm = FakeLLMClient(with_synopsis=True)
    new_items = [
        TimestampedAnalysis(analysis=_analysis("new1111"), committed_at="2024-06-01T00:00:00")
    ]
    _service(llm, case_store, synopsis_store, items=new_items).generate("repo-1")
    user_msg = next(m.content for m in llm.last_messages if m.role == "user")
    assert synopsis_text in user_msg
    assert "Very long original narrative." not in user_msg


def test_incremental_falls_back_to_narrative_when_no_synopsis() -> None:
    """When no synopsis is stored, full narrative is used as context."""
    existing = CaseStudyRecord(
        repository_id="repo-1",
        narrative="## Overview\nOriginal narrative content.",
        commit_count=1,
        hotspot_count=0,
        generated_at="2024-01-01T00:00:00",
        audience="beginner",
    )
    case_store = FakeCaseStudyStore()
    case_store.save_case_study(existing)
    synopsis_store = FakeSynopsisStore()  # empty
    llm = FakeLLMClient(with_synopsis=True)
    new_items = [
        TimestampedAnalysis(analysis=_analysis("new1111"), committed_at="2024-06-01T00:00:00")
    ]
    _service(llm, case_store, synopsis_store, items=new_items).generate("repo-1")
    user_msg = next(m.content for m in llm.last_messages if m.role == "user")
    assert "Original narrative content." in user_msg


# ---------------------------------------------------------------------------
# force=True — synopsis regenerated
# ---------------------------------------------------------------------------


def test_force_regenerates_synopsis() -> None:
    synopsis_store = FakeSynopsisStore(existing="Old synopsis.")
    llm = FakeLLMClient(with_synopsis=True)
    _service(llm, synopsis_store=synopsis_store).generate("repo-1", force=True)
    new_synopsis = synopsis_store.get_synopsis("repo-1")
    assert new_synopsis == "Key patterns: TDD adoption."
    assert new_synopsis != "Old synopsis."
