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
    def __init__(self) -> None:
        self.call_count = 0

    def complete(self, messages: list[LLMMessage]) -> str:
        self.call_count += 1
        return "# Case Study\nGenerated narrative."


class FakeCaseStudyStore:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], CaseStudyRecord] = {}
        self.saved: list[CaseStudyRecord] = []

    def save_case_study(self, record: CaseStudyRecord) -> None:
        self._store[(record.repository_id, record.audience)] = record
        self.saved.append(record)

    def get_case_study(
        self, repository_id: str, audience: str = "beginner"
    ) -> CaseStudyRecord | None:
        return self._store.get((repository_id, audience))


def _service(
    llm: FakeLLMClient,
    store: FakeCaseStudyStore | None = None,
) -> NarrativeService:
    return NarrativeService(
        temporal_reader=FakeTemporalReader(),
        pattern_service=FakePatternService(),
        llm_client=llm,
        case_study_store=store,
    )


def test_generate_calls_llm_when_no_cache() -> None:
    llm = FakeLLMClient()
    store = FakeCaseStudyStore()
    _service(llm, store).generate("repo-1")
    assert llm.call_count == 1


def test_generate_saves_to_store() -> None:
    llm = FakeLLMClient()
    store = FakeCaseStudyStore()
    _service(llm, store).generate("repo-1")
    assert len(store.saved) == 1
    assert store.saved[0].repository_id == "repo-1"
    assert "Case Study" in store.saved[0].narrative


def test_generate_returns_cached_without_llm_call() -> None:
    llm = FakeLLMClient()
    store = FakeCaseStudyStore()
    svc = _service(llm, store)
    svc.generate("repo-1")
    assert llm.call_count == 1
    svc.generate("repo-1")
    assert llm.call_count == 1


def test_force_bypasses_cache() -> None:
    llm = FakeLLMClient()
    store = FakeCaseStudyStore()
    svc = _service(llm, store)
    svc.generate("repo-1")
    svc.generate("repo-1", force=True)
    assert llm.call_count == 2


def test_cached_result_has_correct_fields() -> None:
    llm = FakeLLMClient()
    store = FakeCaseStudyStore()
    svc = _service(llm, store)
    svc.generate("repo-1")
    result = svc.generate("repo-1")
    assert result.repository_id == "repo-1"
    assert result.commit_count == 1
    assert "Case Study" in result.narrative


def test_no_store_still_works() -> None:
    llm = FakeLLMClient()
    result = _service(llm, store=None).generate("repo-1")
    assert result.narrative != ""
    assert llm.call_count == 1


# ---------------------------------------------------------------------------
# Audience-specific caching (Batch 67)
# ---------------------------------------------------------------------------


def test_generate_saves_record_with_correct_audience() -> None:
    llm = FakeLLMClient()
    store = FakeCaseStudyStore()
    svc = _service(llm, store)
    svc.generate("repo-1", audience="beginner")
    assert store.saved[-1].audience == "beginner"


def test_different_audiences_both_call_llm() -> None:
    llm = FakeLLMClient()
    store = FakeCaseStudyStore()
    svc = _service(llm, store)
    svc.generate("repo-1", audience="beginner")
    svc.generate("repo-1", audience="expert")
    assert llm.call_count == 2


def test_same_audience_uses_cache_on_second_call() -> None:
    llm = FakeLLMClient()
    store = FakeCaseStudyStore()
    svc = _service(llm, store)
    svc.generate("repo-1", audience="expert")
    svc.generate("repo-1", audience="expert")
    assert llm.call_count == 1
