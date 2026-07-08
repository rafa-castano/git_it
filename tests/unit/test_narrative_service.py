import logging
from datetime import UTC, datetime
from typing import Literal

import pytest

from git_it.repository_ingestion.application.narrative_service import (
    NarrativeResult,
    NarrativeService,
    OpeningQualityResult,
    check_opening_quality,
)
from git_it.repository_ingestion.application.ports import (
    CaseStudyRecord,
    LLMMessage,
    TimestampedAnalysis,
)
from git_it.repository_ingestion.domain.advisories import AdvisoryEvidence
from git_it.repository_ingestion.domain.analysis import (
    CommitAnalysis,
    CommitCategory,
    RiskLevel,
)
from git_it.repository_ingestion.domain.discussions import DiscussionEvidence
from git_it.repository_ingestion.domain.patterns import (
    BugfixRecurrence,
    CategoryCount,
    CommitTestGrowthSignal,
    Hotspot,
    PatternReport,
    RefactorWave,
)
from git_it.repository_ingestion.domain.project_docs import ProjectDocContent
from git_it.repository_ingestion.domain.releases import ReleaseEvidence


def _make_analysis(sha: str = "abc1234", summary: str = "Added feature") -> CommitAnalysis:
    return CommitAnalysis(
        commit_sha=sha,
        summary=summary,
        category=CommitCategory.FEATURE,
        intent=None,
        intent_is_inferred=True,
        affected_components=["core"],
        risk_level=RiskLevel.LOW,
        confidence=0.8,
        evidence=[],
        limitations=[],
    )


def _make_hotspot(file_path: str = "src/main.py", commit_count: int = 10) -> Hotspot:
    return Hotspot(
        file_path=file_path,
        commit_count=commit_count,
        total_insertions=50,
        total_deletions=20,
    )


def _make_item(
    sha: str = "abc1234",
    summary: str = "Added feature",
    date: str = "2024-01-15T00:00:00",
) -> TimestampedAnalysis:
    return TimestampedAnalysis(analysis=_make_analysis(sha, summary), committed_at=date)


def _make_discussion_evidence(
    discussion_id: str = "d1",
    discussion_url: str = "https://github.com/owner/repo/discussions/1",
    claim_type: Literal["design_rationale", "pain_point"] = "design_rationale",
    summary: str = "The team chose SQLite for local dev simplicity.",
) -> DiscussionEvidence:
    return DiscussionEvidence(
        discussion_id=discussion_id,
        discussion_url=discussion_url,
        claim_type=claim_type,
        summary=summary,
        confidence=0.8,
        limitations=[],
        source_inputs=[discussion_id],
        generated_at=datetime(2024, 1, 1, tzinfo=UTC),
        model="test-model",
    )


class FakeTemporalReader:
    def __init__(self, items: list[TimestampedAnalysis] | None = None) -> None:
        self._items = items or []

    def list_analyses_with_dates(self, repository_id: str) -> list[TimestampedAnalysis]:
        return list(self._items)

    def list_analyses_since(self, repository_id: str, *, since: str) -> list[TimestampedAnalysis]:
        return [item for item in self._items if item.committed_at >= since]


class FakePatternService:
    def __init__(
        self,
        hotspots: list[Hotspot] | None = None,
        report: PatternReport | None = None,
    ) -> None:
        self._report = report
        self._hotspots = hotspots or []
        self.calls: list[str] = []

    def detect(self, repository_id: str, *, hotspot_threshold: int = 5) -> PatternReport:
        self.calls.append(repository_id)
        if self._report is not None:
            return self._report
        return PatternReport(repository_id=repository_id, hotspots=list(self._hotspots))


class FakeLLMClient:
    def __init__(self, response: str = "Educational narrative.") -> None:
        self._response = response
        self.calls: list[list[LLMMessage]] = []

    def complete(self, messages: list[LLMMessage]) -> str:
        self.calls.append(list(messages))
        return self._response


class FakeDiscussionReader:
    def __init__(self, evidence: list[DiscussionEvidence] | None = None) -> None:
        self._evidence = evidence or []

    def get_discussion_evidence(self, repository_id: str) -> list[DiscussionEvidence]:
        return list(self._evidence)


def _make_release_evidence(
    tag_name: str = "v1.0.0",
    release_url: str = "https://github.com/owner/repo/releases/tag/v1.0.0",
    claim_type: str = "feature_release",
    summary: str = "Added support for pgvector-based semantic search.",
) -> ReleaseEvidence:
    return ReleaseEvidence(
        tag_name=tag_name,
        release_url=release_url,
        claim_type=claim_type,  # type: ignore[arg-type]
        summary=summary,
        confidence=0.8,
        limitations=[],
        source_inputs=[tag_name],
        generated_at=datetime(2024, 1, 1, tzinfo=UTC),
        model="test-model",
    )


class FakeReleaseReader:
    def __init__(self, evidence: list[ReleaseEvidence] | None = None) -> None:
        self._evidence = evidence or []

    def get_release_evidence(self, repository_id: str) -> list[ReleaseEvidence]:
        return list(self._evidence)


def _make_advisory_evidence(
    ghsa_id: str = "GHSA-aaaa-bbbb-cccc",
    advisory_url: str = "https://github.com/owner/repo/security/advisories/GHSA-aaaa-bbbb-cccc",
    severity: str = "high",
    summary: str = "A path traversal vulnerability was patched in file upload handling.",
) -> AdvisoryEvidence:
    return AdvisoryEvidence(
        ghsa_id=ghsa_id,
        advisory_url=advisory_url,
        severity=severity,  # type: ignore[arg-type]
        summary=summary,
        confidence=0.8,
        limitations=[],
        source_inputs=[ghsa_id],
        generated_at=datetime(2024, 1, 1, tzinfo=UTC),
        model="test-model",
    )


class FakeAdvisoryReader:
    def __init__(self, evidence: list[AdvisoryEvidence] | None = None) -> None:
        self._evidence = evidence or []

    def get_advisory_evidence(self, repository_id: str) -> list[AdvisoryEvidence]:
        return list(self._evidence)


def _make_project_docs(
    repository_id: str = "repo-1",
    readme_text: str | None = "This project does X.",
    readme_truncated: bool = False,
    changelog_text: str | None = None,
    changelog_truncated: bool = False,
) -> ProjectDocContent:
    return ProjectDocContent(
        repository_id=repository_id,
        readme_text=readme_text,
        readme_truncated=readme_truncated,
        changelog_text=changelog_text,
        changelog_truncated=changelog_truncated,
        captured_at=datetime(2024, 1, 1, tzinfo=UTC),
    )


class FakeProjectDocReader:
    def __init__(self, docs: ProjectDocContent | None = None) -> None:
        self._docs = docs

    def get_project_docs(self, repository_id: str) -> ProjectDocContent | None:
        return self._docs


def _make_service(
    items: list[TimestampedAnalysis] | None = None,
    hotspots: list[Hotspot] | None = None,
    response: str = "A great case study.",
) -> tuple[NarrativeService, FakeLLMClient]:
    client = FakeLLMClient(response)
    service = NarrativeService(
        temporal_reader=FakeTemporalReader(items),
        pattern_service=FakePatternService(hotspots),
        llm_client=client,
    )
    return service, client


def test_generate_returns_narrative_result() -> None:
    service, _ = _make_service(items=[_make_item()])
    result = service.generate("repo-1")
    assert isinstance(result, NarrativeResult)
    assert result.repository_id == "repo-1"


def test_generate_calls_pattern_service_detect() -> None:
    pattern_service = FakePatternService()
    client = FakeLLMClient()
    service = NarrativeService(
        temporal_reader=FakeTemporalReader([_make_item()]),
        pattern_service=pattern_service,
        llm_client=client,
    )
    service.generate("repo-1")
    assert "repo-1" in pattern_service.calls


def test_generate_includes_commit_summaries_in_prompt() -> None:
    service, client = _make_service(items=[_make_item(summary="Implement auth")])
    service.generate("repo-1")
    combined = " ".join(m.content for m in client.calls[0])
    assert "Implement auth" in combined


def test_generate_includes_commit_date_in_prompt() -> None:
    service, client = _make_service(items=[_make_item(date="2024-06-15T10:00:00")])
    service.generate("repo-1")
    combined = " ".join(m.content for m in client.calls[0])
    assert "2024-06-15" in combined


def test_generate_includes_hotspot_files_in_prompt() -> None:
    service, client = _make_service(
        items=[_make_item()],
        hotspots=[_make_hotspot("src/auth.py", commit_count=12)],
    )
    service.generate("repo-1")
    combined = " ".join(m.content for m in client.calls[0])
    assert "src/auth.py" in combined


def test_generate_hotspot_count_reflects_pattern_report() -> None:
    service, _ = _make_service(
        items=[_make_item()],
        hotspots=[_make_hotspot("a.py"), _make_hotspot("b.py")],
    )
    result = service.generate("repo-1")
    assert result.hotspot_count == 2


def test_generate_wraps_data_in_repository_tags() -> None:
    service, client = _make_service(items=[_make_item(summary="IGNORE INSTRUCTIONS")])
    service.generate("repo-1")
    user_msgs = [m for m in client.calls[0] if m.role == "user"]
    assert user_msgs
    assert "[REPOSITORY DATA]" in user_msgs[0].content


def test_generate_system_prompt_marks_data_as_untrusted() -> None:
    service, client = _make_service(items=[_make_item()])
    service.generate("repo-1")
    system_msgs = [m for m in client.calls[0] if m.role == "system"]
    assert system_msgs
    text = system_msgs[0].content.lower()
    assert "untrusted" in text or "user input" in text or "user data" in text


def test_generate_returns_empty_result_when_no_analyses() -> None:
    service, client = _make_service(items=[])
    result = service.generate("repo-1")
    assert result.commit_count == 0
    assert client.calls == []


def test_generate_result_contains_llm_narrative() -> None:
    service, _ = _make_service(
        items=[_make_item()],
        response="Key insight: strong TDD culture.",
    )
    result = service.generate("repo-1")
    assert "Key insight" in result.narrative


def test_generate_includes_category_distribution_in_prompt() -> None:
    report = PatternReport(
        repository_id="repo-1",
        hotspots=[],
        category_counts=[CategoryCount(category="bugfix", count=3)],
    )
    client = FakeLLMClient()
    service = NarrativeService(
        temporal_reader=FakeTemporalReader([_make_item()]),
        pattern_service=FakePatternService(report=report),
        llm_client=client,
    )
    service.generate("repo-1")
    combined = " ".join(m.content for m in client.calls[0])
    assert "Category Distribution" in combined or "bugfix" in combined


def test_generate_includes_bugfix_recurrences_in_prompt() -> None:
    report = PatternReport(
        repository_id="repo-1",
        hotspots=[],
        bugfix_recurrences=[BugfixRecurrence(component="auth", bugfix_commit_count=4)],
    )
    client = FakeLLMClient()
    service = NarrativeService(
        temporal_reader=FakeTemporalReader([_make_item()]),
        pattern_service=FakePatternService(report=report),
        llm_client=client,
    )
    service.generate("repo-1")
    combined = " ".join(m.content for m in client.calls[0])
    assert "auth" in combined


def test_generate_includes_refactor_wave_in_prompt() -> None:
    report = PatternReport(
        repository_id="repo-1",
        hotspots=[],
        refactor_wave=RefactorWave(commit_count=5, refactor_ratio=0.5),
    )
    client = FakeLLMClient()
    service = NarrativeService(
        temporal_reader=FakeTemporalReader([_make_item()]),
        pattern_service=FakePatternService(report=report),
        llm_client=client,
    )
    service.generate("repo-1")
    combined = " ".join(m.content for m in client.calls[0])
    assert "Refactor" in combined or "refactor" in combined


def test_generate_includes_test_growth_signal_in_prompt() -> None:
    report = PatternReport(
        repository_id="repo-1",
        hotspots=[],
        test_growth_signal=CommitTestGrowthSignal(
            test_commit_count=3, bugfix_commit_count=4, test_to_bugfix_ratio=0.75
        ),
    )
    client = FakeLLMClient()
    service = NarrativeService(
        temporal_reader=FakeTemporalReader([_make_item()]),
        pattern_service=FakePatternService(report=report),
        llm_client=client,
    )
    service.generate("repo-1")
    combined = " ".join(m.content for m in client.calls[0])
    assert "Test" in combined or "test" in combined


def test_system_prompt_uses_spec_004_narrative_structure() -> None:
    service, client = _make_service(items=[_make_item()])
    service.generate("repo-1")
    system_msgs = [m for m in client.calls[0] if m.role == "system"]
    assert system_msgs
    text = system_msgs[0].content
    assert "Timeline" in text
    assert "Engineering Lessons" in text


# ---------------------------------------------------------------------------
# Audience-level system prompts (Batch 67)
# ---------------------------------------------------------------------------


def test_generate_beginner_audience_injects_beginner_block() -> None:
    service, client = _make_service(items=[_make_item()])
    service.generate("repo-1", audience="beginner")
    system_text = next(m.content for m in client.calls[0] if m.role == "system")
    assert "students or people new to software development" in system_text


def test_generate_expert_audience_injects_expert_block() -> None:
    service, client = _make_service(items=[_make_item()])
    service.generate("repo-1", audience="expert")
    system_text = next(m.content for m in client.calls[0] if m.role == "system")
    assert "senior engineers and software architects" in system_text


def test_generate_unknown_audience_falls_back_to_beginner() -> None:
    service, client = _make_service(items=[_make_item()])
    service.generate("repo-1", audience="invalid")
    system_text = next(m.content for m in client.calls[0] if m.role == "system")
    assert "plain language" in system_text


def test_generate_does_not_include_removed_sections() -> None:
    service, client = _make_service(items=[_make_item()])
    service.generate("repo-1")
    system_text = next(m.content for m in client.calls[0] if m.role == "system")
    assert "Evidence Index" not in system_text
    assert "## Limitations" not in system_text


# ---------------------------------------------------------------------------
# Anti-generic-opening validator (Batch 88 / spec 015)
# ---------------------------------------------------------------------------


def test_check_opening_quality_flags_known_generic_boilerplate() -> None:
    narrative = (
        "## Overview\n"
        "This case study traces what happened in the weeks that followed, using the "
        "commit history as evidence.\n\n"
        "## Timeline\n"
        "Some timeline content."
    )
    result = check_opening_quality(narrative)
    assert isinstance(result, OpeningQualityResult)
    assert result.is_generic is True
    assert result.matched_phrase is not None


def test_check_opening_quality_passes_repo_specific_opening() -> None:
    narrative = (
        "## Overview\n"
        "Git It is a Python FastAPI service that mines GitHub repositories with "
        "PyDriller and turns commit history into LLM-generated case studies.\n\n"
        "## Timeline\n"
        "Some timeline content."
    )
    result = check_opening_quality(narrative)
    assert result.is_generic is False
    assert result.matched_phrase is None


def test_check_opening_quality_handles_empty_narrative() -> None:
    result = check_opening_quality("")
    assert result.is_generic is False
    assert result.opening_text == ""


def test_check_opening_quality_handles_narrative_without_section_header() -> None:
    narrative = "This case study traces what happened in the weeks that followed."
    result = check_opening_quality(narrative)
    assert result.is_generic is True


def test_check_opening_quality_only_inspects_first_paragraph() -> None:
    narrative = (
        "## Overview\n"
        "Git It mines GitHub repositories and turns commit history into case studies.\n\n"
        "This case study traces what happened in the weeks that followed, but this is a "
        "second paragraph and should not be inspected."
    )
    result = check_opening_quality(narrative)
    assert result.is_generic is False


def test_check_opening_quality_does_not_flag_specific_opening_using_a_common_temporal_phrase() -> (
    None
):
    """ "In the weeks that followed" is ordinary English, not boilerplate on its own.

    Found via live QA (Playwright sweep, 2026-07-04): a genuinely repo-specific opening
    naming the exact stack and integrations was flagged generic solely because it ended
    with this common temporal phrase. The other list entries already catch the actual
    known-bad pattern (see test_check_opening_quality_flags_known_generic_boilerplate),
    so this phrase does not need to be a standalone trigger.
    """
    narrative = (
        "## Overview\n"
        "Odysseus is a self-hosted AI agent platform that integrates a conversational "
        "assistant with real-world productivity tools, backed by a Python/FastAPI "
        "backend. The project launched as v1.0 and then entered an intensive two-week "
        "stabilization sprint, producing 230 additional commits in the weeks that "
        "followed.\n\n"
        "## Timeline\n"
        "Some timeline content."
    )
    result = check_opening_quality(narrative)
    assert result.is_generic is False
    assert result.matched_phrase is None


def test_generate_logs_warning_when_narrative_opening_is_generic(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    service, _ = _make_service(
        items=[_make_item()],
        response=(
            "## Overview\n"
            "This case study traces what happened in the weeks that followed, using "
            "the commit history as evidence.\n\n"
            "## Timeline\nsome content"
        ),
    )
    service.generate("repo-1")
    assert any("generic" in record.message.lower() for record in caplog.records)


def test_generate_does_not_log_warning_for_repo_specific_opening(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    service, _ = _make_service(
        items=[_make_item()],
        response=(
            "## Overview\n"
            "Git It mines GitHub repositories and turns commit history into "
            "educational case studies.\n\n"
            "## Timeline\nsome content"
        ),
    )
    service.generate("repo-1")
    assert not any("generic" in record.message.lower() for record in caplog.records)


def test_system_prompt_instructs_against_generic_opening() -> None:
    service, client = _make_service(items=[_make_item()])
    service.generate("repo-1")
    system_text = next(m.content for m in client.calls[0] if m.role == "system")
    lowered = system_text.lower()
    assert "repository-specific" in lowered or "repo-specific" in lowered
    assert "this case study traces" in lowered


# ---------------------------------------------------------------------------
# Discussion evidence integration (Batch 110 / spec 022)
# ---------------------------------------------------------------------------


def test_build_user_message_includes_discussion_evidence_block() -> None:
    items = [_make_item()]
    report = PatternReport(repository_id="repo-1", hotspots=[])
    evidence = [
        _make_discussion_evidence(
            discussion_id="d1",
            discussion_url="https://github.com/owner/repo/discussions/1",
            claim_type="design_rationale",
            summary="Chose SQLite for simplicity",
        ),
        _make_discussion_evidence(
            discussion_id="d2",
            discussion_url="https://github.com/owner/repo/discussions/2",
            claim_type="pain_point",
            summary="Users reported flaky CI on Windows",
        ),
    ]
    message = NarrativeService._build_user_message(items, report, evidence)
    assert "## Discussion Evidence" in message
    assert "[design_rationale] Chose SQLite for simplicity" in message
    assert "(source: https://github.com/owner/repo/discussions/1)" in message
    assert "[pain_point] Users reported flaky CI on Windows" in message
    assert "(source: https://github.com/owner/repo/discussions/2)" in message


def test_build_user_message_omits_discussion_evidence_block_when_empty() -> None:
    items = [_make_item()]
    report = PatternReport(repository_id="repo-1", hotspots=[])
    message = NarrativeService._build_user_message(items, report, [])
    assert "## Discussion Evidence" not in message


def test_build_incremental_user_message_includes_discussion_evidence_block() -> None:
    report = PatternReport(repository_id="repo-1", hotspots=[])
    evidence = [
        _make_discussion_evidence(
            discussion_id="d1",
            discussion_url="https://github.com/owner/repo/discussions/1",
            claim_type="design_rationale",
            summary="Chose SQLite for simplicity",
        )
    ]
    message = NarrativeService._build_incremental_user_message(
        new_items=[_make_item()],
        prior_context="Prior narrative content.",
        report=report,
        discussion_evidence=evidence,
    )
    assert "## Discussion Evidence" in message
    assert "[design_rationale] Chose SQLite for simplicity" in message
    assert "(source: https://github.com/owner/repo/discussions/1)" in message


def test_build_incremental_user_message_omits_discussion_evidence_block_when_empty() -> None:
    report = PatternReport(repository_id="repo-1", hotspots=[])
    message = NarrativeService._build_incremental_user_message(
        new_items=[_make_item()],
        prior_context="Prior narrative content.",
        report=report,
        discussion_evidence=[],
    )
    assert "## Discussion Evidence" not in message


def test_generate_with_discussion_reader_includes_evidence_in_user_message() -> None:
    evidence = [
        _make_discussion_evidence(
            discussion_id="d1",
            discussion_url="https://github.com/owner/repo/discussions/1",
            claim_type="design_rationale",
            summary="Chose SQLite for simplicity",
        )
    ]
    client = FakeLLMClient()
    service = NarrativeService(
        temporal_reader=FakeTemporalReader([_make_item()]),
        pattern_service=FakePatternService(),
        llm_client=client,
        discussion_reader=FakeDiscussionReader(evidence),
    )
    service.generate("repo-1")
    user_msgs = [m for m in client.calls[0] if m.role == "user"]
    assert user_msgs
    assert "## Discussion Evidence" in user_msgs[0].content
    assert "Chose SQLite for simplicity" in user_msgs[0].content
    assert "(source: https://github.com/owner/repo/discussions/1)" in user_msgs[0].content


def test_generate_without_discussion_reader_omits_evidence_block() -> None:
    service, client = _make_service(items=[_make_item()])
    service.generate("repo-1")
    user_msgs = [m for m in client.calls[0] if m.role == "user"]
    assert user_msgs
    assert "## Discussion Evidence" not in user_msgs[0].content


def test_discussion_evidence_lines_use_only_evidence_fields_no_raw_discussion_text() -> None:
    """The rendered line shape is exactly '[claim_type] summary  (source: url)' —
    no raw Discussion title/body ever exists at this layer to leak."""
    items = [_make_item()]
    report = PatternReport(repository_id="repo-1", hotspots=[])
    evidence = [
        _make_discussion_evidence(
            discussion_id="d1",
            discussion_url="https://github.com/owner/repo/discussions/1",
            claim_type="pain_point",
            summary="Windows CI is flaky",
        )
    ]
    message = NarrativeService._build_user_message(items, report, evidence)
    evidence_lines = [
        line for line in message.splitlines() if line.strip().startswith("- [pain_point]")
    ]
    assert evidence_lines == [
        "- [pain_point] Windows CI is flaky  (source: https://github.com/owner/repo/discussions/1)"
    ]


def test_both_system_prompts_instruct_discussion_source_url_fidelity() -> None:
    service, client = _make_service(items=[_make_item()])
    service.generate("repo-1")
    system_text = next(m.content for m in client.calls[0] if m.role == "system")
    lowered = system_text.lower()
    assert "discussion evidence" in lowered
    assert "source" in lowered

    incremental_client = FakeLLMClient()
    incremental_service = NarrativeService(
        temporal_reader=FakeTemporalReader(
            [
                _make_item(date="2024-01-01T00:00:00"),
                _make_item(sha="def5678", date="2024-06-01T00:00:00"),
            ]
        ),
        pattern_service=FakePatternService(),
        llm_client=incremental_client,
    )
    existing = CaseStudyRecord(
        repository_id="repo-1",
        narrative="Existing narrative",
        commit_count=1,
        hotspot_count=0,
        generated_at="2024-01-02T00:00:00",
        audience="beginner",
    )
    incremental_service._generate_incremental(
        "repo-1",
        new_items=[_make_item(sha="def5678", date="2024-06-01T00:00:00")],
        existing=existing,
    )
    incremental_system_text = next(
        m.content for m in incremental_client.calls[0] if m.role == "system"
    )
    incremental_lowered = incremental_system_text.lower()
    assert "discussion evidence" in incremental_lowered
    assert "source" in incremental_lowered


def test_both_system_prompts_request_full_repository_relative_file_paths() -> None:
    # Spec 029 AC-09: both the initial and incremental narrative prompts must
    # instruct the model to reference files as their full repository-relative
    # path in backticks, not a bare basename.
    service, client = _make_service(items=[_make_item()])
    service.generate("repo-1")
    system_text = next(m.content for m in client.calls[0] if m.role == "system")
    assert "full repository-relative" in system_text.lower()
    assert "`ports.py`" in system_text  # the discouraged bare-basename example
    assert "genuinely unknown" in system_text.lower()

    incremental_client = FakeLLMClient()
    incremental_service = NarrativeService(
        temporal_reader=FakeTemporalReader(
            [
                _make_item(date="2024-01-01T00:00:00"),
                _make_item(sha="def5678", date="2024-06-01T00:00:00"),
            ]
        ),
        pattern_service=FakePatternService(),
        llm_client=incremental_client,
    )
    existing = CaseStudyRecord(
        repository_id="repo-1",
        narrative="Existing narrative",
        commit_count=1,
        hotspot_count=0,
        generated_at="2024-01-02T00:00:00",
        audience="beginner",
    )
    incremental_service._generate_incremental(
        "repo-1",
        new_items=[_make_item(sha="def5678", date="2024-06-01T00:00:00")],
        existing=existing,
    )
    incremental_system_text = next(
        m.content for m in incremental_client.calls[0] if m.role == "system"
    )
    incremental_lowered = incremental_system_text.lower()
    assert "full repository-relative" in incremental_lowered
    assert "`ports.py`" in incremental_system_text
    assert "genuinely unknown" in incremental_lowered


# ---------------------------------------------------------------------------
# Project documentation integration (Batch 133 / spec 025)
# ---------------------------------------------------------------------------


def test_build_user_message_includes_project_doc_block_when_present() -> None:
    items = [_make_item()]
    report = PatternReport(repository_id="repo-1", hotspots=[])
    docs = _make_project_docs(readme_text="Git It analyzes GitHub repository history.")
    message = NarrativeService._build_user_message(items, report, [], docs)
    assert "## Project Documentation" in message
    assert "Git It analyzes GitHub repository history." in message


def test_build_user_message_omits_project_doc_block_when_none() -> None:
    items = [_make_item()]
    report = PatternReport(repository_id="repo-1", hotspots=[])
    message = NarrativeService._build_user_message(items, report, [], None)
    assert "## Project Documentation" not in message


def test_build_incremental_user_message_includes_project_doc_block_when_present() -> None:
    report = PatternReport(repository_id="repo-1", hotspots=[])
    docs = _make_project_docs(readme_text="Git It analyzes GitHub repository history.")
    message = NarrativeService._build_incremental_user_message(
        new_items=[_make_item()],
        prior_context="Prior narrative content.",
        report=report,
        discussion_evidence=[],
        project_docs=docs,
    )
    assert "## Project Documentation" in message
    assert "Git It analyzes GitHub repository history." in message


def test_build_incremental_user_message_omits_project_doc_block_when_none() -> None:
    report = PatternReport(repository_id="repo-1", hotspots=[])
    message = NarrativeService._build_incremental_user_message(
        new_items=[_make_item()],
        prior_context="Prior narrative content.",
        report=report,
        discussion_evidence=[],
        project_docs=None,
    )
    assert "## Project Documentation" not in message


def test_generate_with_project_doc_reader_includes_docs_in_user_message() -> None:
    docs = _make_project_docs(readme_text="Git It analyzes GitHub repository history.")
    client = FakeLLMClient()
    service = NarrativeService(
        temporal_reader=FakeTemporalReader([_make_item()]),
        pattern_service=FakePatternService(),
        llm_client=client,
        project_doc_reader=FakeProjectDocReader(docs),
    )
    service.generate("repo-1")
    user_msgs = [m for m in client.calls[0] if m.role == "user"]
    assert user_msgs
    assert "## Project Documentation" in user_msgs[0].content
    assert "Git It analyzes GitHub repository history." in user_msgs[0].content


def test_generate_without_project_doc_reader_omits_project_doc_block() -> None:
    service, client = _make_service(items=[_make_item()])
    service.generate("repo-1")
    user_msgs = [m for m in client.calls[0] if m.role == "user"]
    assert user_msgs
    assert "## Project Documentation" not in user_msgs[0].content


def test_generate_when_reader_returns_none_omits_project_doc_block() -> None:
    client = FakeLLMClient()
    service = NarrativeService(
        temporal_reader=FakeTemporalReader([_make_item()]),
        pattern_service=FakePatternService(),
        llm_client=client,
        project_doc_reader=FakeProjectDocReader(None),
    )
    service.generate("repo-1")
    user_msgs = [m for m in client.calls[0] if m.role == "user"]
    assert user_msgs
    assert "## Project Documentation" not in user_msgs[0].content


def test_project_doc_block_renders_readme_only() -> None:
    items = [_make_item()]
    report = PatternReport(repository_id="repo-1", hotspots=[])
    docs = _make_project_docs(readme_text="README purpose statement.", changelog_text=None)
    message = NarrativeService._build_user_message(items, report, [], docs)
    assert "### README" in message
    assert "README purpose statement." in message
    assert "### CHANGELOG" not in message


def test_project_doc_block_renders_changelog_only() -> None:
    items = [_make_item()]
    report = PatternReport(repository_id="repo-1", hotspots=[])
    docs = _make_project_docs(readme_text=None, changelog_text="## 1.0.0 - Initial release")
    message = NarrativeService._build_user_message(items, report, [], docs)
    assert "### CHANGELOG" in message
    assert "## 1.0.0 - Initial release" in message
    assert "### README" not in message


def test_project_doc_block_renders_both_readme_and_changelog() -> None:
    items = [_make_item()]
    report = PatternReport(repository_id="repo-1", hotspots=[])
    docs = _make_project_docs(
        readme_text="README purpose statement.",
        changelog_text="## 1.0.0 - Initial release",
    )
    message = NarrativeService._build_user_message(items, report, [], docs)
    assert "### README" in message
    assert "README purpose statement." in message
    assert "### CHANGELOG" in message
    assert "## 1.0.0 - Initial release" in message


def test_project_doc_block_frames_content_as_project_own_documentation() -> None:
    """The block must not present README/CHANGELOG text as an independently-verified
    fact — it must be framed as the project's own stated description (spec 025)."""
    items = [_make_item()]
    report = PatternReport(repository_id="repo-1", hotspots=[])
    docs = _make_project_docs(readme_text="Some project purpose.")
    message = NarrativeService._build_user_message(items, report, [], docs)
    lowered = message.lower()
    assert "project documentation" in lowered
    assert "own" in lowered
    assert "not an independently-verified fact" in lowered


def test_project_doc_block_has_no_source_citation_suffix() -> None:
    """Unlike Discussion Evidence, Project Documentation has no evidence_ref/URL — no
    '(source: ...)' suffix should appear for this block (spec 025 locked decision)."""
    items = [_make_item()]
    report = PatternReport(repository_id="repo-1", hotspots=[])
    docs = _make_project_docs(readme_text="Some project purpose.")
    message = NarrativeService._build_user_message(items, report, [], docs)
    doc_section_start = message.index("## Project Documentation")
    doc_section = message[doc_section_start:]
    assert "(source:" not in doc_section


# ---------------------------------------------------------------------------
# Release and Security Advisory evidence integration (Batch 142 / spec 026)
# ---------------------------------------------------------------------------


def test_build_user_message_includes_release_evidence_block() -> None:
    items = [_make_item()]
    report = PatternReport(repository_id="repo-1", hotspots=[])
    evidence = [
        _make_release_evidence(
            tag_name="v1.0.0",
            release_url="https://github.com/owner/repo/releases/tag/v1.0.0",
            claim_type="feature_release",
            summary="Added support for pgvector-based semantic search.",
        ),
        _make_release_evidence(
            tag_name="v2.0.0",
            release_url="https://github.com/owner/repo/releases/tag/v2.0.0",
            claim_type="breaking_change",
            summary="Removed the legacy v1 REST endpoints.",
        ),
    ]
    message = NarrativeService._build_user_message(
        items, report, [], None, release_evidence=evidence
    )
    assert "## Release History" in message
    assert "[feature_release] Added support for pgvector-based semantic search." in message
    assert "(source: https://github.com/owner/repo/releases/tag/v1.0.0)" in message
    assert "[breaking_change] Removed the legacy v1 REST endpoints." in message
    assert "(source: https://github.com/owner/repo/releases/tag/v2.0.0)" in message


def test_build_user_message_omits_release_evidence_block_when_empty() -> None:
    items = [_make_item()]
    report = PatternReport(repository_id="repo-1", hotspots=[])
    message = NarrativeService._build_user_message(items, report, [], None, release_evidence=[])
    assert "## Release History" not in message


def test_build_incremental_user_message_includes_release_evidence_block() -> None:
    report = PatternReport(repository_id="repo-1", hotspots=[])
    evidence = [
        _make_release_evidence(
            tag_name="v1.0.0",
            release_url="https://github.com/owner/repo/releases/tag/v1.0.0",
            claim_type="feature_release",
            summary="Added support for pgvector-based semantic search.",
        )
    ]
    message = NarrativeService._build_incremental_user_message(
        new_items=[_make_item()],
        prior_context="Prior narrative content.",
        report=report,
        discussion_evidence=[],
        release_evidence=evidence,
    )
    assert "## Release History" in message
    assert "[feature_release] Added support for pgvector-based semantic search." in message
    assert "(source: https://github.com/owner/repo/releases/tag/v1.0.0)" in message


def test_build_incremental_user_message_omits_release_evidence_block_when_empty() -> None:
    report = PatternReport(repository_id="repo-1", hotspots=[])
    message = NarrativeService._build_incremental_user_message(
        new_items=[_make_item()],
        prior_context="Prior narrative content.",
        report=report,
        discussion_evidence=[],
        release_evidence=[],
    )
    assert "## Release History" not in message


def test_build_user_message_includes_advisory_evidence_block() -> None:
    items = [_make_item()]
    report = PatternReport(repository_id="repo-1", hotspots=[])
    evidence = [
        _make_advisory_evidence(
            ghsa_id="GHSA-aaaa-bbbb-cccc",
            advisory_url=("https://github.com/owner/repo/security/advisories/GHSA-aaaa-bbbb-cccc"),
            severity="high",
            summary="A path traversal vulnerability was patched in file upload handling.",
        ),
        _make_advisory_evidence(
            ghsa_id="GHSA-dddd-eeee-ffff",
            advisory_url=("https://github.com/owner/repo/security/advisories/GHSA-dddd-eeee-ffff"),
            severity="critical",
            summary="A remote code execution vulnerability was patched.",
        ),
    ]
    message = NarrativeService._build_user_message(
        items, report, [], None, advisory_evidence=evidence
    )
    assert "## Security Advisories" in message
    assert "[high] A path traversal vulnerability was patched in file upload handling." in message
    assert (
        "(source: https://github.com/owner/repo/security/advisories/GHSA-aaaa-bbbb-cccc)" in message
    )
    assert "[critical] A remote code execution vulnerability was patched." in message
    assert (
        "(source: https://github.com/owner/repo/security/advisories/GHSA-dddd-eeee-ffff)" in message
    )


def test_build_user_message_omits_advisory_evidence_block_when_empty() -> None:
    items = [_make_item()]
    report = PatternReport(repository_id="repo-1", hotspots=[])
    message = NarrativeService._build_user_message(items, report, [], None, advisory_evidence=[])
    assert "## Security Advisories" not in message


def test_build_incremental_user_message_includes_advisory_evidence_block() -> None:
    report = PatternReport(repository_id="repo-1", hotspots=[])
    evidence = [
        _make_advisory_evidence(
            ghsa_id="GHSA-aaaa-bbbb-cccc",
            advisory_url=("https://github.com/owner/repo/security/advisories/GHSA-aaaa-bbbb-cccc"),
            severity="high",
            summary="A path traversal vulnerability was patched in file upload handling.",
        )
    ]
    message = NarrativeService._build_incremental_user_message(
        new_items=[_make_item()],
        prior_context="Prior narrative content.",
        report=report,
        discussion_evidence=[],
        advisory_evidence=evidence,
    )
    assert "## Security Advisories" in message
    assert "[high] A path traversal vulnerability was patched in file upload handling." in message
    assert (
        "(source: https://github.com/owner/repo/security/advisories/GHSA-aaaa-bbbb-cccc)" in message
    )


def test_build_incremental_user_message_omits_advisory_evidence_block_when_empty() -> None:
    report = PatternReport(repository_id="repo-1", hotspots=[])
    message = NarrativeService._build_incremental_user_message(
        new_items=[_make_item()],
        prior_context="Prior narrative content.",
        report=report,
        discussion_evidence=[],
        advisory_evidence=[],
    )
    assert "## Security Advisories" not in message


def test_generate_with_release_and_advisory_readers_includes_both_blocks() -> None:
    release_evidence = [
        _make_release_evidence(
            tag_name="v1.0.0",
            release_url="https://github.com/owner/repo/releases/tag/v1.0.0",
            claim_type="feature_release",
            summary="Added support for pgvector-based semantic search.",
        )
    ]
    advisory_evidence = [
        _make_advisory_evidence(
            ghsa_id="GHSA-aaaa-bbbb-cccc",
            advisory_url=("https://github.com/owner/repo/security/advisories/GHSA-aaaa-bbbb-cccc"),
            severity="high",
            summary="A path traversal vulnerability was patched in file upload handling.",
        )
    ]
    client = FakeLLMClient()
    service = NarrativeService(
        temporal_reader=FakeTemporalReader([_make_item()]),
        pattern_service=FakePatternService(),
        llm_client=client,
        release_evidence_reader=FakeReleaseReader(release_evidence),
        advisory_evidence_reader=FakeAdvisoryReader(advisory_evidence),
    )
    service.generate("repo-1")
    user_msgs = [m for m in client.calls[0] if m.role == "user"]
    assert user_msgs
    assert "## Release History" in user_msgs[0].content
    assert "(source: https://github.com/owner/repo/releases/tag/v1.0.0)" in user_msgs[0].content
    assert "## Security Advisories" in user_msgs[0].content
    assert (
        "(source: https://github.com/owner/repo/security/advisories/GHSA-aaaa-bbbb-cccc)"
        in user_msgs[0].content
    )


def test_generate_without_release_or_advisory_readers_omits_both_blocks() -> None:
    service, client = _make_service(items=[_make_item()])
    service.generate("repo-1")
    user_msgs = [m for m in client.calls[0] if m.role == "user"]
    assert user_msgs
    assert "## Release History" not in user_msgs[0].content
    assert "## Security Advisories" not in user_msgs[0].content


def test_release_evidence_lines_use_only_evidence_fields_no_raw_release_body() -> None:
    """The rendered line shape is exactly '[claim_type] summary  (source: url)' — no raw
    Release body/notes text ever exists at this layer to leak."""
    items = [_make_item()]
    report = PatternReport(repository_id="repo-1", hotspots=[])
    evidence = [
        _make_release_evidence(
            tag_name="v1.0.0",
            release_url="https://github.com/owner/repo/releases/tag/v1.0.0",
            claim_type="feature_release",
            summary="Added semantic search.",
        )
    ]
    message = NarrativeService._build_user_message(
        items, report, [], None, release_evidence=evidence
    )
    evidence_lines = [
        line for line in message.splitlines() if line.strip().startswith("- [feature_release]")
    ]
    assert evidence_lines == [
        "- [feature_release] Added semantic search."
        "  (source: https://github.com/owner/repo/releases/tag/v1.0.0)"
    ]


def test_advisory_evidence_lines_use_only_evidence_fields_no_raw_description() -> None:
    """The rendered line shape is exactly '[severity] summary  (source: url)' — no raw
    SecurityAdvisory description text ever exists at this layer to leak."""
    items = [_make_item()]
    report = PatternReport(repository_id="repo-1", hotspots=[])
    evidence = [
        _make_advisory_evidence(
            ghsa_id="GHSA-aaaa-bbbb-cccc",
            advisory_url=("https://github.com/owner/repo/security/advisories/GHSA-aaaa-bbbb-cccc"),
            severity="high",
            summary="Path traversal patched.",
        )
    ]
    message = NarrativeService._build_user_message(
        items, report, [], None, advisory_evidence=evidence
    )
    evidence_lines = [line for line in message.splitlines() if line.strip().startswith("- [high]")]
    assert evidence_lines == [
        "- [high] Path traversal patched."
        "  (source: https://github.com/owner/repo/security/advisories/GHSA-aaaa-bbbb-cccc)"
    ]


def test_both_system_prompts_instruct_release_and_advisory_source_url_fidelity() -> None:
    service, client = _make_service(items=[_make_item()])
    service.generate("repo-1")
    system_text = next(m.content for m in client.calls[0] if m.role == "system")
    lowered = system_text.lower()
    assert "release history" in lowered
    assert "security advisories" in lowered
    assert "source" in lowered

    incremental_client = FakeLLMClient()
    incremental_service = NarrativeService(
        temporal_reader=FakeTemporalReader(
            [
                _make_item(date="2024-01-01T00:00:00"),
                _make_item(sha="def5678", date="2024-06-01T00:00:00"),
            ]
        ),
        pattern_service=FakePatternService(),
        llm_client=incremental_client,
    )
    existing = CaseStudyRecord(
        repository_id="repo-1",
        narrative="Existing narrative",
        commit_count=1,
        hotspot_count=0,
        generated_at="2024-01-02T00:00:00",
        audience="beginner",
    )
    incremental_service._generate_incremental(
        "repo-1",
        new_items=[_make_item(sha="def5678", date="2024-06-01T00:00:00")],
        existing=existing,
    )
    incremental_system_text = next(
        m.content for m in incremental_client.calls[0] if m.role == "system"
    )
    incremental_lowered = incremental_system_text.lower()
    assert "release history" in incremental_lowered
    assert "security advisories" in incremental_lowered
    assert "source" in incremental_lowered
