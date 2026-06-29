"""
Tests for incremental case study update (Batch 42).

Behavior:
- No existing case study → send ALL analyses to LLM
- Existing case study + new analyses → send ONLY new analyses + existing narrative as context
- Existing case study, no new analyses → skip LLM entirely, return existing
"""

from git_it.repository_ingestion.application.narrative_service import (
    NarrativeResult,
    NarrativeService,
)
from git_it.repository_ingestion.application.ports import (
    CaseStudyRecord,
    LLMMessage,
    TimestampedAnalysis,
)
from git_it.repository_ingestion.domain.analysis import CommitAnalysis, CommitCategory, RiskLevel
from git_it.repository_ingestion.domain.patterns import PatternReport

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _analysis(sha: str = "abc1234", summary: str = "Added feature") -> CommitAnalysis:
    return CommitAnalysis(
        commit_sha=sha,
        summary=summary,
        category=CommitCategory.FEATURE,
        confidence=0.9,
        risk_level=RiskLevel.LOW,
        intent=None,
        intent_is_inferred=False,
        affected_components=[],
        evidence=[],
        limitations=[],
    )


def _item(sha: str = "abc1234", summary: str = "Added feature") -> TimestampedAnalysis:
    return TimestampedAnalysis(analysis=_analysis(sha, summary), committed_at="2024-01-15T00:00:00")


def _case_study_record(
    narrative: str = "# Existing Case Study\n\nsome content",
    commit_count: int = 3,
    generated_at: str = "2024-06-01T10:00:00",
) -> CaseStudyRecord:
    return CaseStudyRecord(
        repository_id="repo-1",
        narrative=narrative,
        commit_count=commit_count,
        hotspot_count=0,
        generated_at=generated_at,
    )


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class RecordingLLMClient:
    """Records all messages received and returns a configurable response."""

    def __init__(self, response: str = "# Updated Case Study\n\ncontent") -> None:
        self._response = response
        self.calls: list[list[LLMMessage]] = []

    def complete(self, messages: list[LLMMessage]) -> str:
        self.calls.append(list(messages))
        return self._response

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def last_messages_text(self) -> str:
        if not self.calls:
            return ""
        return " ".join(m.content for m in self.calls[-1])


class FakeIncrementalTemporalReader:
    """Returns all analyses, and optionally a filtered subset since a given timestamp."""

    def __init__(
        self,
        all_items: list[TimestampedAnalysis] | None = None,
        new_items: list[TimestampedAnalysis] | None = None,
    ) -> None:
        self._all_items = all_items or []
        self._new_items = new_items if new_items is not None else list(self._all_items)

    def list_analyses_with_dates(self, repository_id: str) -> list[TimestampedAnalysis]:
        return list(self._all_items)

    def list_analyses_since(self, repository_id: str, *, since: str) -> list[TimestampedAnalysis]:
        return list(self._new_items)


class FakePatternService:
    def detect(self, repository_id: str, *, hotspot_threshold: int = 5) -> PatternReport:
        return PatternReport(repository_id=repository_id, hotspots=[])


class FakeCaseStudyStore:
    def __init__(self, existing: CaseStudyRecord | None = None) -> None:
        self._record = existing
        self.saved: list[CaseStudyRecord] = []

    def save_case_study(self, record: CaseStudyRecord) -> None:
        self._record = record
        self.saved.append(record)

    def get_case_study(
        self, repository_id: str, audience: str = "intermediate"
    ) -> CaseStudyRecord | None:
        return self._record


def _make_service(
    all_items: list[TimestampedAnalysis] | None = None,
    new_items: list[TimestampedAnalysis] | None = None,
    existing: CaseStudyRecord | None = None,
    response: str = "# Updated Case Study\n\ncontent",
) -> tuple[NarrativeService, RecordingLLMClient, FakeCaseStudyStore]:
    client = RecordingLLMClient(response)
    store = FakeCaseStudyStore(existing=existing)
    service = NarrativeService(
        temporal_reader=FakeIncrementalTemporalReader(
            all_items=all_items,
            new_items=new_items,
        ),
        pattern_service=FakePatternService(),
        llm_client=client,
        case_study_store=store,
    )
    return service, client, store


# ---------------------------------------------------------------------------
# Tests: first run (no existing case study)
# ---------------------------------------------------------------------------


def test_no_existing_case_study_uses_all_analyses() -> None:
    """First run: all analyses must be sent to the LLM."""
    items = [_item("sha1"), _item("sha2"), _item("sha3")]
    service, client, _ = _make_service(all_items=items, existing=None)

    service.generate("repo-1")

    assert client.call_count == 1
    combined = client.last_messages_text()
    assert "sha1" in combined
    assert "sha2" in combined
    assert "sha3" in combined


def test_no_existing_case_study_no_narrative_section_in_prompt() -> None:
    """First run: the prompt must NOT contain the 'Existing Case Study' section."""
    items = [_item("sha1")]
    service, client, _ = _make_service(all_items=items, existing=None)

    service.generate("repo-1")

    combined = client.last_messages_text()
    assert "Existing Case Study" not in combined
    assert "Existing narrative" not in combined


def test_no_existing_case_study_result_is_narrative_result() -> None:
    """First run result is a NarrativeResult with correct repository_id."""
    service, _, _ = _make_service(all_items=[_item()], existing=None)
    result = service.generate("repo-1")
    assert isinstance(result, NarrativeResult)
    assert result.repository_id == "repo-1"


# ---------------------------------------------------------------------------
# Tests: incremental update (existing + new analyses)
# ---------------------------------------------------------------------------


def test_existing_with_new_analyses_sends_only_delta() -> None:
    """Update run: only new analyses (delta) must be sent to LLM."""
    old_items = [_item("old1"), _item("old2"), _item("old3")]
    new_items = [_item("new1"), _item("new2"), _item("new3")]
    existing = _case_study_record(commit_count=3)

    service, client, _ = _make_service(
        all_items=old_items + new_items,
        new_items=new_items,
        existing=existing,
    )

    service.generate("repo-1")

    assert client.call_count == 1
    combined = client.last_messages_text()
    # New analyses MUST appear
    assert "new1" in combined
    assert "new2" in combined
    assert "new3" in combined
    # Old analyses must NOT be resent
    assert "old1" not in combined
    assert "old2" not in combined
    assert "old3" not in combined


def test_incremental_prompt_includes_existing_narrative() -> None:
    """Update run: the existing narrative must appear in the LLM message."""
    existing = _case_study_record(narrative="# Prior narrative\n\nVery important insight.")
    service, client, _ = _make_service(
        all_items=[_item("old1")],
        new_items=[_item("new1")],
        existing=existing,
    )

    service.generate("repo-1")

    combined = client.last_messages_text()
    assert "Prior narrative" in combined
    assert "Very important insight" in combined


def test_incremental_prompt_labels_existing_narrative() -> None:
    """Update run: the prompt must label the existing case study clearly."""
    existing = _case_study_record(narrative="Old content here.")
    service, client, _ = _make_service(
        all_items=[_item("old1")],
        new_items=[_item("new1")],
        existing=existing,
    )

    service.generate("repo-1")

    combined = client.last_messages_text()
    assert "Existing Case Study" in combined or "existing" in combined.lower()


def test_incremental_prompt_labels_new_commits_section() -> None:
    """Update run: the prompt must have a section for the new commits."""
    existing = _case_study_record()
    service, client, _ = _make_service(
        all_items=[_item("old1")],
        new_items=[_item("new1", summary="Auth fix commit")],
        existing=existing,
    )

    service.generate("repo-1")

    combined = client.last_messages_text()
    assert "New Commits" in combined or "new commits" in combined.lower()
    assert "Auth fix commit" in combined


def test_incremental_update_saves_new_case_study() -> None:
    """Update run: the result must be saved back to the store."""
    existing = _case_study_record(narrative="Old.")
    service, _, store = _make_service(
        all_items=[_item("old1")],
        new_items=[_item("new1")],
        existing=existing,
        response="# New narrative",
    )

    service.generate("repo-1")

    assert len(store.saved) == 1
    assert "New narrative" in store.saved[0].narrative


# ---------------------------------------------------------------------------
# Tests: no new analyses (skip LLM)
# ---------------------------------------------------------------------------


def test_no_new_analyses_returns_existing_without_llm_call() -> None:
    """When there are no new analyses, the LLM must NOT be called."""
    existing = _case_study_record(narrative="# Cached study")
    service, client, _ = _make_service(
        all_items=[_item("old1"), _item("old2")],
        new_items=[],  # no new analyses since last generation
        existing=existing,
    )

    result = service.generate("repo-1")

    assert client.call_count == 0
    assert result.narrative == "# Cached study"
    assert result.repository_id == "repo-1"


def test_no_new_analyses_returns_existing_commit_count() -> None:
    """When skipping LLM, commit_count should reflect the stored value."""
    existing = _case_study_record(commit_count=42)
    service, client, _ = _make_service(
        all_items=[_item("old1")],
        new_items=[],
        existing=existing,
    )

    result = service.generate("repo-1")

    assert client.call_count == 0
    assert result.commit_count == 42


def test_no_new_analyses_does_not_save_to_store() -> None:
    """When skipping LLM, nothing should be written back to the store."""
    existing = _case_study_record(narrative="# Stable")
    service, _, store = _make_service(
        all_items=[_item("old1")],
        new_items=[],
        existing=existing,
    )

    service.generate("repo-1")

    assert store.saved == []


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------


def test_empty_all_analyses_returns_empty_result() -> None:
    """No analyses at all → empty NarrativeResult, LLM not called."""
    service, client, _ = _make_service(all_items=[], new_items=[], existing=None)

    result = service.generate("repo-1")

    assert client.call_count == 0
    assert result.commit_count == 0
    assert result.narrative == ""


def test_single_new_analysis_triggers_incremental_update() -> None:
    """A single new analysis is enough to trigger LLM call in incremental mode."""
    existing = _case_study_record(commit_count=5)
    service, client, _ = _make_service(
        all_items=[_item("old1"), _item("new1")],
        new_items=[_item("new1", summary="Critical security patch")],
        existing=existing,
    )

    service.generate("repo-1")

    assert client.call_count == 1
    assert "Critical security patch" in client.last_messages_text()


def test_force_flag_sends_all_analyses_ignoring_cache() -> None:
    """force=True must bypass incremental logic and send all analyses."""
    items = [_item("sha1"), _item("sha2")]
    existing = _case_study_record(commit_count=1)
    service, client, _ = _make_service(
        all_items=items,
        new_items=[_item("sha2")],  # only one new
        existing=existing,
    )

    service.generate("repo-1", force=True)

    assert client.call_count == 1
    combined = client.last_messages_text()
    # Both must appear (all_items, not just new_items)
    assert "sha1" in combined
    assert "sha2" in combined


def test_incremental_result_has_updated_commit_count() -> None:
    """After incremental update, commit_count should reflect total (all) analyses."""
    old_items = [_item("sha1"), _item("sha2")]
    new_items_only = [_item("sha3"), _item("sha4")]
    existing = _case_study_record(commit_count=2)

    service, _, store = _make_service(
        all_items=old_items + new_items_only,
        new_items=new_items_only,
        existing=existing,
    )

    result = service.generate("repo-1")

    # commit_count should be the total number of analyses
    assert result.commit_count == 4
