import dataclasses
import re
from pathlib import Path

from git_it.repository_ingestion.application.ports import (
    CommitAnalysisReader,
    CommitDateReader,
    CommitSummaryReader,
    CommitSummaryRecord,
    FileChurnRecord,
    FileEvidenceReader,
    FileFactReader,
    FileOwnershipRecord,
    OwnershipReader,
    PatternSynthesisClient,
)
from git_it.repository_ingestion.domain.analysis import CommitAnalysis, CommitCategory
from git_it.repository_ingestion.domain.patterns import (
    ArchitecturalShift,
    BugfixRecurrence,
    CategoryCount,
    CommitTestGrowthSignal,
    DependencyMigration,
    Hotspot,
    OwnershipConcentration,
    PatternReport,
    RefactorWave,
    RevertSignal,
)

_DEFAULT_HOTSPOT_THRESHOLD = 5

# Common words and short tokens to filter out of migration detection
_MIGRATION_NOISE_WORDS: frozenset[str] = frozenset(
    {"the", "a", "an", "it", "this", "that", "my", "our", "its", "old", "new"}
)

_MIGRATION_PATTERNS: list[re.Pattern[str]] = [
    # "migrate from X to Y" / "migration from X to Y"
    re.compile(r"migrat\w* from (\w[\w\-\.]+) to (\w[\w\-\.]+)", re.IGNORECASE),
    # "replace X with Y" / "replace X by Y"
    re.compile(r"replace (\w[\w\-\.]+) with (\w[\w\-\.]+)", re.IGNORECASE),
    re.compile(r"replace (\w[\w\-\.]+) by (\w[\w\-\.]+)", re.IGNORECASE),
    # "switch from X to Y"
    re.compile(r"switch from (\w[\w\-\.]+) to (\w[\w\-\.]+)", re.IGNORECASE),
    # "move from X to Y"
    re.compile(r"move from (\w[\w\-\.]+) to (\w[\w\-\.]+)", re.IGNORECASE),
]

_NEW_TOP_LEVEL_DIR_MIN_FILES = 5
_MODULE_EXTRACTION_OTHER_DIRS_MIN = 3
_MODULE_EXTRACTION_OTHER_DIR_MIN_FILES = 5
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
        synthesis_client: PatternSynthesisClient | None = None,
    ) -> None:
        self._reader = reader
        self._analysis_reader = analysis_reader
        self._ownership_reader = ownership_reader
        self._commit_summary_reader = commit_summary_reader
        self._commit_date_reader = commit_date_reader
        self._file_evidence_reader = file_evidence_reader
        self._synthesis_client = synthesis_client

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
        test_growth_signal: CommitTestGrowthSignal | None = None

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
        summaries: list[CommitSummaryRecord] = []
        if self._commit_summary_reader is not None:
            summaries = self._commit_summary_reader.list_commit_messages(repository_id)
            revert_signal = _compute_revert_signal(
                summaries, threshold=revert_threshold, date_map=date_map
            )

        # Dependency migrations (rule-based, no LLM)
        dependency_migrations = _compute_dependency_migrations(summaries, date_map=date_map)

        # Architectural shifts (rule-based, no LLM)
        architectural_shifts = _compute_architectural_shifts(
            churn_records, date_map=date_map, file_evidence=file_evidence
        )

        report = PatternReport(
            repository_id=repository_id,
            hotspots=hotspots,
            category_counts=category_counts,
            bugfix_recurrences=bugfix_recurrences,
            refactor_wave=refactor_wave,
            revert_signal=revert_signal,
            test_growth_signal=test_growth_signal,
            ownership_concentrations=ownership_concentrations,
            dependency_migrations=dependency_migrations,
            architectural_shifts=architectural_shifts,
        )

        if self._synthesis_client is not None and _report_has_patterns(report):
            explanations = self._synthesis_client.synthesize(report)
            report = dataclasses.replace(report, explanations=explanations)

        return report


def _report_has_patterns(report: PatternReport) -> bool:
    """Return True if the report contains at least one non-trivial pattern."""
    return bool(
        report.hotspots
        or report.bugfix_recurrences
        or report.refactor_wave is not None
        or report.revert_signal is not None
        or report.test_growth_signal is not None
        or report.ownership_concentrations
        or report.dependency_migrations
        or report.architectural_shifts
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
) -> CommitTestGrowthSignal | None:
    bugfix_analyses = [a for a in analyses if a.category == CommitCategory.BUGFIX]
    test_analyses = [a for a in analyses if a.category == CommitCategory.TEST]
    bugfix_count = len(bugfix_analyses)
    test_count = len(test_analyses)
    if bugfix_count == 0 or test_count == 0:
        return None
    ratio = round(test_count / bugfix_count, 2)
    evidence_shas = _top_shas_from_analyses(test_analyses + bugfix_analyses, date_map=date_map)
    return CommitTestGrowthSignal(
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


def _is_noisy_token(token: str) -> bool:
    """Return True if the token is a common word or too short to be a dependency name."""
    return len(token) < 3 or token.lower() in _MIGRATION_NOISE_WORDS


def _compute_dependency_migrations(
    summaries: list[CommitSummaryRecord],
    *,
    date_map: dict[str, str],
) -> list[DependencyMigration]:
    """Detect dependency migration patterns from commit messages using regex."""
    # Map (from_dep, to_dep) -> list of matching SHAs
    migration_shas: dict[tuple[str, str], list[str]] = {}

    for summary in summaries:
        first_line = summary.message.split("\n")[0]
        for pattern in _MIGRATION_PATTERNS:
            for match in pattern.finditer(first_line):
                from_token = match.group(1).lower()
                to_token = match.group(2).lower()
                if _is_noisy_token(from_token) or _is_noisy_token(to_token):
                    continue
                key = (from_token, to_token)
                migration_shas.setdefault(key, [])
                if summary.sha not in migration_shas[key]:
                    migration_shas[key].append(summary.sha)

    result: list[DependencyMigration] = []
    for (from_dep, to_dep), shas in migration_shas.items():
        commit_count = len(shas)
        evidence = tuple(shas[:5])
        confidence = round(min(1.0, commit_count / 3.0), 10)
        result.append(
            DependencyMigration(
                from_dependency=from_dep,
                to_dependency=to_dep,
                commit_count=commit_count,
                evidence_commit_shas=evidence,
                time_range=_time_range_for_shas(evidence, date_map),
                confidence=confidence,
            )
        )

    return sorted(result, key=lambda m: m.commit_count, reverse=True)


def _compute_architectural_shifts(
    file_churn: list[FileChurnRecord],
    *,
    date_map: dict[str, str],
    file_evidence: dict[str, tuple[str, ...]],
) -> list[ArchitecturalShift]:
    """Detect architectural shifts by analyzing top-level directory structure."""
    if not file_churn:
        return []

    # Count files per top-level directory
    top_dirs: dict[str, list[str]] = {}
    for record in file_churn:
        parts = Path(record.file_path).parts
        if len(parts) >= 2:
            top_dir = parts[0]
            top_dirs.setdefault(top_dir, []).append(record.file_path)

    if len(top_dirs) <= 1:
        # Only 1 top-level dir — no structural signal
        return []

    total_files = sum(len(files) for files in top_dirs.values())
    result: list[ArchitecturalShift] = []

    # Detect new_top_level_dir: dirs with >= _NEW_TOP_LEVEL_DIR_MIN_FILES files
    significant_dirs: dict[str, int] = {}
    for top_dir, files in top_dirs.items():
        count = len(files)
        if count >= _NEW_TOP_LEVEL_DIR_MIN_FILES:
            significant_dirs[top_dir] = count
            confidence = round(min(1.0, count / 20.0), 10)
            # Gather evidence SHAs from the most-churned file in this dir
            dir_evidence: tuple[str, ...] = ()
            if file_evidence:
                for fpath in files:
                    shas = file_evidence.get(fpath, ())
                    if len(shas) > len(dir_evidence):
                        dir_evidence = shas
            result.append(
                ArchitecturalShift(
                    shift_type="new_top_level_dir",
                    description=f"Directory '{top_dir}/' contains {count} tracked files",
                    evidence_commit_shas=dir_evidence,
                    time_range=_time_range_for_shas(dir_evidence, date_map),
                    confidence=confidence,
                )
            )

    # Detect module_extraction: dominant dir with >= 3 other dirs each having >= 5 files
    if total_files > 0 and significant_dirs:
        dominant = max(significant_dirs, key=lambda d: significant_dirs[d])
        dominant_ratio = significant_dirs[dominant] / total_files
        other_large_dirs = [
            d
            for d, c in significant_dirs.items()
            if d != dominant and c >= _MODULE_EXTRACTION_OTHER_DIR_MIN_FILES
        ]
        if dominant_ratio > 0.3 and len(other_large_dirs) >= _MODULE_EXTRACTION_OTHER_DIRS_MIN - 1:
            result.append(
                ArchitecturalShift(
                    shift_type="module_extraction",
                    description=(
                        "Multiple significant top-level modules detected "
                        "— extraction likely occurred"
                    ),
                    evidence_commit_shas=(),
                    time_range=None,
                    confidence=0.6,
                )
            )

    return result
