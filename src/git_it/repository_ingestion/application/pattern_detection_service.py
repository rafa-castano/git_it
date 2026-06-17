from git_it.repository_ingestion.application.ports import (
    CommitAnalysisReader,
    CommitDateReader,
    CommitSummaryReader,
    CommitSummaryRecord,
    FileEvidenceReader,
    FileFactReader,
    FileOwnershipRecord,
    OwnershipReader,
)
from git_it.repository_ingestion.domain.analysis import CommitAnalysis, CommitCategory
from git_it.repository_ingestion.domain.patterns import (
    BugfixRecurrence,
    CategoryCount,
    Hotspot,
    OwnershipConcentration,
    PatternReport,
    RefactorWave,
    RevertSignal,
    TestGrowthSignal,
)

_DEFAULT_HOTSPOT_THRESHOLD = 5
_DEFAULT_BUGFIX_RECURRENCE_THRESHOLD = 2
_DEFAULT_REFACTOR_WAVE_THRESHOLD = 3
_DEFAULT_OWNERSHIP_THRESHOLD = 1
_DEFAULT_REVERT_THRESHOLD = 1


class PatternDetectionService:
    def __init__(
        self,
        *,
        reader: FileFactReader,
        analysis_reader: CommitAnalysisReader | None = None,
        ownership_reader: OwnershipReader | None = None,
        commit_summary_reader: CommitSummaryReader | None = None,
        commit_date_reader: CommitDateReader | None = None,
        file_evidence_reader: FileEvidenceReader | None = None,
    ) -> None:
        self._reader = reader
        self._analysis_reader = analysis_reader
        self._ownership_reader = ownership_reader
        self._commit_summary_reader = commit_summary_reader
        self._commit_date_reader = commit_date_reader
        self._file_evidence_reader = file_evidence_reader

    def detect(
        self,
        repository_id: str,
        *,
        hotspot_threshold: int = _DEFAULT_HOTSPOT_THRESHOLD,
        bugfix_recurrence_threshold: int = _DEFAULT_BUGFIX_RECURRENCE_THRESHOLD,
        refactor_wave_threshold: int = _DEFAULT_REFACTOR_WAVE_THRESHOLD,
        ownership_threshold: int = _DEFAULT_OWNERSHIP_THRESHOLD,
        revert_threshold: int = _DEFAULT_REVERT_THRESHOLD,
    ) -> PatternReport:
        # Pre-fetch enrichment data if readers are available
        date_map: dict[str, str] = (
            self._commit_date_reader.get_commit_date_map(repository_id)
            if self._commit_date_reader is not None
            else {}
        )
        file_evidence: dict[str, tuple[str, ...]] = (
            self._file_evidence_reader.get_file_evidence_commits(repository_id)
            if self._file_evidence_reader is not None
            else {}
        )

        churn_records = self._reader.get_file_churn(repository_id)
        hotspots = sorted(
            (
                _make_hotspot(
                    r.file_path,
                    r.commit_count,
                    r.total_insertions,
                    r.total_deletions,
                    file_evidence,
                    date_map,
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
                analyses, threshold=bugfix_recurrence_threshold, date_map=date_map
            )
            refactor_wave = _compute_refactor_wave(
                analyses, threshold=refactor_wave_threshold, date_map=date_map
            )
            test_growth_signal = _compute_test_growth_signal(analyses, date_map=date_map)

        ownership_concentrations: list[OwnershipConcentration] = []
        if self._ownership_reader is not None:
            ownership_records = self._ownership_reader.get_file_ownership(repository_id)
            ownership_concentrations = _compute_ownership_concentrations(
                ownership_records,
                threshold=ownership_threshold,
                file_evidence=file_evidence,
                date_map=date_map,
            )

        revert_signal: RevertSignal | None = None
        if self._commit_summary_reader is not None:
            summaries = self._commit_summary_reader.list_commit_messages(repository_id)
            revert_signal = _compute_revert_signal(
                summaries, threshold=revert_threshold, date_map=date_map
            )

        return PatternReport(
            repository_id=repository_id,
            hotspots=hotspots,
            category_counts=category_counts,
            bugfix_recurrences=bugfix_recurrences,
            refactor_wave=refactor_wave,
            revert_signal=revert_signal,
            test_growth_signal=test_growth_signal,
            ownership_concentrations=ownership_concentrations,
        )


def _time_range_for_shas(shas: tuple[str, ...], date_map: dict[str, str]) -> tuple[str, str] | None:
    dates = [date_map[s] for s in shas if s in date_map]
    if not dates:
        return None
    return (min(dates), max(dates))


def _make_hotspot(
    file_path: str,
    commit_count: int,
    total_insertions: int,
    total_deletions: int,
    file_evidence: dict[str, tuple[str, ...]],
    date_map: dict[str, str],
) -> Hotspot:
    shas = file_evidence.get(file_path, ())
    confidence = round(min(1.0, commit_count / 20.0), 3)
    return Hotspot(
        file_path=file_path,
        commit_count=commit_count,
        total_insertions=total_insertions,
        total_deletions=total_deletions,
        evidence_commit_shas=shas,
        time_range=_time_range_for_shas(shas, date_map),
        confidence=confidence,
    )


def _top_shas_from_analyses(
    analyses: list[CommitAnalysis],
    *,
    date_map: dict[str, str],
    limit: int = 5,
) -> tuple[str, ...]:
    """Return up to `limit` most-recent commit SHAs from analyses, sorted by committed_at."""

    def _sort_key(a: CommitAnalysis) -> str:
        return date_map.get(a.commit_sha, a.commit_sha)

    sorted_analyses = sorted(analyses, key=_sort_key, reverse=True)
    return tuple(a.commit_sha for a in sorted_analyses[:limit])


def _compute_test_growth_signal(
    analyses: list[CommitAnalysis], *, date_map: dict[str, str]
) -> TestGrowthSignal | None:
    bugfix_analyses = [a for a in analyses if a.category == CommitCategory.BUGFIX]
    test_analyses = [a for a in analyses if a.category == CommitCategory.TEST]
    bugfix_count = len(bugfix_analyses)
    test_count = len(test_analyses)
    if bugfix_count == 0 or test_count == 0:
        return None
    ratio = round(test_count / bugfix_count, 2)
    evidence_shas = _top_shas_from_analyses(test_analyses + bugfix_analyses, date_map=date_map)
    return TestGrowthSignal(
        test_commit_count=test_count,
        bugfix_commit_count=bugfix_count,
        test_to_bugfix_ratio=ratio,
        evidence_commit_shas=evidence_shas,
        time_range=_time_range_for_shas(evidence_shas, date_map),
        confidence=round(min(1.0, ratio / 2.0), 3),
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
    analyses: list[CommitAnalysis], *, threshold: int, date_map: dict[str, str]
) -> RefactorWave | None:
    total = len(analyses)
    if total == 0:
        return None
    refactor_analyses = [a for a in analyses if a.category == CommitCategory.REFACTOR]
    refactor_count = len(refactor_analyses)
    if refactor_count < threshold:
        return None
    ratio = round(refactor_count / total, 2)
    evidence_shas = _top_shas_from_analyses(refactor_analyses, date_map=date_map)
    return RefactorWave(
        commit_count=refactor_count,
        refactor_ratio=ratio,
        evidence_commit_shas=evidence_shas,
        time_range=_time_range_for_shas(evidence_shas, date_map),
        confidence=round(min(1.0, ratio * 2.0), 3),
    )


def _compute_bugfix_recurrences(
    analyses: list[CommitAnalysis], *, threshold: int, date_map: dict[str, str]
) -> list[BugfixRecurrence]:
    component_analyses: dict[str, list[CommitAnalysis]] = {}
    for a in analyses:
        if a.category == CommitCategory.BUGFIX:
            for component in a.affected_components:
                component_analyses.setdefault(component, []).append(a)
    result = []
    for comp, comp_analyses in component_analyses.items():
        cnt = len(comp_analyses)
        if cnt < threshold:
            continue
        evidence_shas = _top_shas_from_analyses(comp_analyses, date_map=date_map)
        result.append(
            BugfixRecurrence(
                component=comp,
                bugfix_commit_count=cnt,
                evidence_commit_shas=evidence_shas,
                time_range=_time_range_for_shas(evidence_shas, date_map),
                confidence=round(min(1.0, cnt / 10.0), 3),
            )
        )
    return sorted(result, key=lambda r: r.bugfix_commit_count, reverse=True)


def _compute_ownership_concentrations(
    records: list[FileOwnershipRecord],
    *,
    threshold: int,
    file_evidence: dict[str, tuple[str, ...]],
    date_map: dict[str, str],
) -> list[OwnershipConcentration]:
    result = []
    for r in records:
        if r.author_count > threshold:
            continue
        shas = file_evidence.get(r.file_path, ())
        confidence = round(1.0 - min(1.0, (r.author_count - 1) / 5.0), 3)
        result.append(
            OwnershipConcentration(
                file_path=r.file_path,
                author_count=r.author_count,
                commit_count=r.commit_count,
                evidence_commit_shas=shas,
                time_range=_time_range_for_shas(shas, date_map),
                confidence=confidence,
            )
        )
    return sorted(result, key=lambda c: c.commit_count, reverse=True)


def _compute_revert_signal(
    summaries: list[CommitSummaryRecord], *, threshold: int, date_map: dict[str, str]
) -> RevertSignal | None:
    total = len(summaries)
    if total == 0:
        return None
    revert_summaries = [s for s in summaries if s.message.lower().startswith("revert")]
    revert_count = len(revert_summaries)
    if revert_count < threshold:
        return None
    ratio = round(revert_count / total, 2)
    evidence_shas = tuple(
        s.sha
        for s in sorted(
            revert_summaries,
            key=lambda s: date_map.get(s.sha, s.sha),
            reverse=True,
        )[:5]
    )
    return RevertSignal(
        revert_count=revert_count,
        revert_ratio=ratio,
        evidence_commit_shas=evidence_shas,
        time_range=_time_range_for_shas(evidence_shas, date_map),
        confidence=round(min(1.0, ratio * 5.0), 3),
    )
