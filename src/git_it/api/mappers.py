"""API mappers — pure functions that convert domain objects to API response schemas."""

from git_it.api.schemas import (
    ArchitecturalShiftSchema,
    BugfixRecurrenceSchema,
    CategoryCountItem,
    CommitTestGrowthSignalSchema,
    DependencyMigrationSchema,
    HotspotItem,
    LanguageItem,
    OwnershipConcentrationSchema,
    PatternExplanationSchema,
    PatternReportResponse,
    RefactorWaveSchema,
    RevertSignalSchema,
)
from git_it.repository_ingestion.domain.patterns import PatternReport
from git_it.repository_ingestion.domain.repo_metadata import LanguageBreakdown


def map_languages(languages: tuple[LanguageBreakdown, ...]) -> list[LanguageItem]:
    """Convert a language byte-breakdown into percent-annotated API items.

    Returns [] for an empty input (avoids a division by zero). Order is
    preserved from the input (GitHub's API already returns languages ordered
    by byte count descending; this function does not re-sort).
    """
    total = sum(lang.bytes for lang in languages)
    if total <= 0:
        return []
    return [
        LanguageItem(
            language=lang.language,
            bytes=lang.bytes,
            percent=round(lang.bytes / total * 100, 1),
        )
        for lang in languages
    ]


def map_pattern_report(report: PatternReport) -> PatternReportResponse:
    """Convert a domain PatternReport to a PatternReportResponse schema."""
    hotspots = [
        HotspotItem(
            file_path=h.file_path,
            commit_count=h.commit_count,
            churn=h.churn,
            confidence=h.confidence,
            evidence_commit_shas=list(h.evidence_commit_shas),
            time_range=list(h.time_range) if h.time_range is not None else None,
        )
        for h in report.hotspots
    ]

    refactor_wave = (
        RefactorWaveSchema(
            commit_count=report.refactor_wave.commit_count,
            refactor_ratio=report.refactor_wave.refactor_ratio,
            evidence_commit_shas=list(report.refactor_wave.evidence_commit_shas),
            time_range=(
                list(report.refactor_wave.time_range) if report.refactor_wave.time_range else None
            ),
            confidence=report.refactor_wave.confidence,
        )
        if report.refactor_wave is not None
        else None
    )

    revert_signal = (
        RevertSignalSchema(
            revert_count=report.revert_signal.revert_count,
            revert_ratio=report.revert_signal.revert_ratio,
            evidence_commit_shas=list(report.revert_signal.evidence_commit_shas),
            time_range=(
                list(report.revert_signal.time_range) if report.revert_signal.time_range else None
            ),
            confidence=report.revert_signal.confidence,
        )
        if report.revert_signal is not None
        else None
    )

    test_growth_signal = (
        CommitTestGrowthSignalSchema(
            test_commit_count=report.test_growth_signal.test_commit_count,
            bugfix_commit_count=report.test_growth_signal.bugfix_commit_count,
            test_to_bugfix_ratio=report.test_growth_signal.test_to_bugfix_ratio,
            evidence_commit_shas=list(report.test_growth_signal.evidence_commit_shas),
            time_range=(
                list(report.test_growth_signal.time_range)
                if report.test_growth_signal.time_range
                else None
            ),
            confidence=report.test_growth_signal.confidence,
        )
        if report.test_growth_signal is not None
        else None
    )

    bugfix_recurrences = [
        BugfixRecurrenceSchema(
            component=r.component,
            bugfix_commit_count=r.bugfix_commit_count,
            evidence_commit_shas=list(r.evidence_commit_shas),
            time_range=list(r.time_range) if r.time_range else None,
            confidence=r.confidence,
        )
        for r in report.bugfix_recurrences
    ]

    ownership_concentrations = [
        OwnershipConcentrationSchema(
            file_path=r.file_path,
            author_count=r.author_count,
            commit_count=r.commit_count,
            evidence_commit_shas=list(r.evidence_commit_shas),
            time_range=list(r.time_range) if r.time_range else None,
            confidence=r.confidence,
        )
        for r in report.ownership_concentrations
    ]

    dependency_migrations = [
        DependencyMigrationSchema(
            from_dependency=r.from_dependency,
            to_dependency=r.to_dependency,
            commit_count=r.commit_count,
            evidence_commit_shas=list(r.evidence_commit_shas),
            time_range=list(r.time_range) if r.time_range else None,
            confidence=r.confidence,
        )
        for r in report.dependency_migrations
    ]

    architectural_shifts = [
        ArchitecturalShiftSchema(
            shift_type=r.shift_type,
            description=r.description,
            evidence_commit_shas=list(r.evidence_commit_shas),
            time_range=list(r.time_range) if r.time_range else None,
            confidence=r.confidence,
        )
        for r in report.architectural_shifts
    ]

    explanations = [
        PatternExplanationSchema(
            pattern_type=e.pattern_type,
            pattern_key=e.pattern_key,
            why_it_matters=e.why_it_matters,
            engineer_takeaway=e.engineer_takeaway,
            confidence_note=e.confidence_note,
        )
        for e in report.explanations
    ]

    category_counts = [
        CategoryCountItem(category=cc.category, count=cc.count) for cc in report.category_counts
    ]

    return PatternReportResponse(
        repository_id=report.repository_id,
        hotspots=hotspots,
        refactor_wave=refactor_wave,
        revert_signal=revert_signal,
        test_growth_signal=test_growth_signal,
        bugfix_recurrences=bugfix_recurrences,
        ownership_concentrations=ownership_concentrations,
        dependency_migrations=dependency_migrations,
        architectural_shifts=architectural_shifts,
        explanations=explanations,
        category_counts=category_counts,
    )
