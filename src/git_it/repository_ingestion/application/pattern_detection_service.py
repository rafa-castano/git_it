from git_it.repository_ingestion.application.ports import CommitAnalysisReader, FileFactReader
from git_it.repository_ingestion.domain.analysis import CommitAnalysis, CommitCategory
from git_it.repository_ingestion.domain.patterns import (
    BugfixRecurrence,
    CategoryCount,
    Hotspot,
    PatternReport,
    RefactorWave,
    TestGrowthSignal,
)

_DEFAULT_HOTSPOT_THRESHOLD = 5
_DEFAULT_BUGFIX_RECURRENCE_THRESHOLD = 2
_DEFAULT_REFACTOR_WAVE_THRESHOLD = 3


class PatternDetectionService:
    def __init__(
        self,
        *,
        reader: FileFactReader,
        analysis_reader: CommitAnalysisReader | None = None,
    ) -> None:
        self._reader = reader
        self._analysis_reader = analysis_reader

    def detect(
        self,
        repository_id: str,
        *,
        hotspot_threshold: int = _DEFAULT_HOTSPOT_THRESHOLD,
        bugfix_recurrence_threshold: int = _DEFAULT_BUGFIX_RECURRENCE_THRESHOLD,
        refactor_wave_threshold: int = _DEFAULT_REFACTOR_WAVE_THRESHOLD,
    ) -> PatternReport:
        churn_records = self._reader.get_file_churn(repository_id)
        hotspots = sorted(
            (
                Hotspot(
                    file_path=r.file_path,
                    commit_count=r.commit_count,
                    total_insertions=r.total_insertions,
                    total_deletions=r.total_deletions,
                )
                for r in churn_records
                if r.commit_count >= hotspot_threshold
            ),
            key=lambda h: h.commit_count,
            reverse=True,
        )

        category_counts: list[CategoryCount] = []
        bugfix_recurrences: list[BugfixRecurrence] = []
        refactor_wave: RefactorWave | None = None

        test_growth_signal: TestGrowthSignal | None = None

        if self._analysis_reader is not None:
            analyses = self._analysis_reader.list_analyses(repository_id)
            category_counts = _compute_category_counts(analyses)
            bugfix_recurrences = _compute_bugfix_recurrences(
                analyses, threshold=bugfix_recurrence_threshold
            )
            refactor_wave = _compute_refactor_wave(analyses, threshold=refactor_wave_threshold)
            test_growth_signal = _compute_test_growth_signal(analyses)

        return PatternReport(
            repository_id=repository_id,
            hotspots=hotspots,
            category_counts=category_counts,
            bugfix_recurrences=bugfix_recurrences,
            refactor_wave=refactor_wave,
            test_growth_signal=test_growth_signal,
        )


def _compute_test_growth_signal(analyses: list[CommitAnalysis]) -> TestGrowthSignal | None:
    bugfix_count = sum(1 for a in analyses if a.category == CommitCategory.BUGFIX)
    test_count = sum(1 for a in analyses if a.category == CommitCategory.TEST)
    if bugfix_count == 0 or test_count == 0:
        return None
    return TestGrowthSignal(
        test_commit_count=test_count,
        bugfix_commit_count=bugfix_count,
        test_to_bugfix_ratio=round(test_count / bugfix_count, 2),
    )


def _compute_category_counts(analyses: list[CommitAnalysis]) -> list[CategoryCount]:
    counts: dict[str, int] = {}
    for a in analyses:
        counts[a.category.value] = counts.get(a.category.value, 0) + 1
    return sorted(
        [CategoryCount(category=cat, count=cnt) for cat, cnt in counts.items()],
        key=lambda c: c.count,
        reverse=True,
    )


def _compute_refactor_wave(
    analyses: list[CommitAnalysis], *, threshold: int
) -> RefactorWave | None:
    total = len(analyses)
    if total == 0:
        return None
    refactor_count = sum(1 for a in analyses if a.category == CommitCategory.REFACTOR)
    if refactor_count < threshold:
        return None
    return RefactorWave(
        commit_count=refactor_count,
        refactor_ratio=round(refactor_count / total, 2),
    )


def _compute_bugfix_recurrences(
    analyses: list[CommitAnalysis], *, threshold: int
) -> list[BugfixRecurrence]:
    component_counts: dict[str, int] = {}
    for a in analyses:
        if a.category == CommitCategory.BUGFIX:
            for component in a.affected_components:
                component_counts[component] = component_counts.get(component, 0) + 1
    return sorted(
        [
            BugfixRecurrence(component=comp, bugfix_commit_count=cnt)
            for comp, cnt in component_counts.items()
            if cnt >= threshold
        ],
        key=lambda r: r.bugfix_commit_count,
        reverse=True,
    )
