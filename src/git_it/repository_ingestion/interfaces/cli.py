import argparse
import hashlib
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from git_it.repository_ingestion.application.analysis_service import (
    AnalysisResult,
    RepositoryAnalysisService,
)
from git_it.repository_ingestion.application.commit_query_service import (
    CommitRecord,
    RepositoryCommitQueryService,
)
from git_it.repository_ingestion.application.narrative_service import NarrativeResult
from git_it.repository_ingestion.application.service import IngestionResult
from git_it.repository_ingestion.composition import (
    build_commit_analysis_service,
    build_narrative_service,
    build_pattern_detection_service,
    build_repository_analysis_service,
    build_repository_commit_query_service,
    build_repository_ingestion_service,
)
from git_it.repository_ingestion.domain.analysis import CommitAnalysis
from git_it.repository_ingestion.domain.patterns import PatternReport
from git_it.repository_ingestion.domain.url_contract import parse_repository_url


class IngestionService(Protocol):
    def ingest(self, raw_url: str) -> IngestionResult: ...


class ServiceFactory(Protocol):
    def __call__(self, *, project_root: Path, repository_id: str) -> IngestionService: ...


class CommitQueryService(Protocol):
    def list_commits(
        self,
        repository_id: str,
        *,
        limit: int | None = None,
        order: str = "newest",
        since: str | None = None,
        until: str | None = None,
    ) -> list[CommitRecord]: ...


class CommitQueryFactory(Protocol):
    def __call__(self, *, project_root: Path, repository_id: str) -> CommitQueryService: ...


class AnalysisService(Protocol):
    def analyze(
        self,
        repository_id: str,
        *,
        limit: int | None = None,
    ) -> AnalysisResult: ...


class AnalysisFactory(Protocol):
    def __call__(
        self, *, project_root: Path, repository_id: str, model: str
    ) -> AnalysisService: ...


class CommitBatchService(Protocol):
    def analyze_commits(
        self,
        repository_id: str,
        *,
        limit: int | None = None,
        order: str = "newest",
        since: str | None = None,
        until: str | None = None,
    ) -> list[CommitAnalysis]: ...

    async def analyze_commits_async(
        self,
        repository_id: str,
        *,
        limit: int | None = None,
        order: str = "newest",
        since: str | None = None,
        until: str | None = None,
        concurrency: int = 5,
    ) -> list[CommitAnalysis]: ...

    def estimate_llm_calls(
        self,
        repository_id: str,
        *,
        limit: int | None = None,
        order: str = "newest",
        since: str | None = None,
        until: str | None = None,
    ) -> int: ...


class CommitAnalysisFactory(Protocol):
    def __call__(
        self, *, project_root: Path, repository_id: str, model: str, sample_model: str | None
    ) -> CommitBatchService: ...


class PatternService(Protocol):
    def detect(self, repository_id: str, *, hotspot_threshold: int = ...) -> PatternReport: ...


class PatternFactory(Protocol):
    def __call__(self, *, project_root: Path, repository_id: str) -> PatternService: ...


class NarrativeGeneratorService(Protocol):
    def generate(self, repository_id: str, *, force: bool = ...) -> NarrativeResult: ...


class NarrativeFactory(Protocol):
    def __call__(
        self, *, project_root: Path, repository_id: str, model: str
    ) -> NarrativeGeneratorService: ...


class AnalysisStoreReader(Protocol):
    def list_analyses(
        self, repository_id: str, *, limit: int | None = None
    ) -> list[CommitAnalysis]: ...

    def get_analysis(self, *, repository_id: str, commit_sha: str) -> CommitAnalysis | None: ...


class ListAnalysesFactory(Protocol):
    def __call__(self, *, project_root: Path, repository_id: str) -> AnalysisStoreReader: ...


_DEFAULT_BUDGET_THRESHOLD = 50


def _default_budget_confirm(count: int) -> bool:
    import sys

    if not sys.stdin.isatty():
        print(f"Warning: {count} LLM calls planned. Proceeding in non-interactive mode.")
        return True
    answer = input(f"{count} LLM calls planned. Proceed? [y/N] ").strip().lower()
    return answer in ("y", "yes")


_FAILED_STATUSES = {
    "FAILED_VALIDATION",
    "FAILED_FETCH",
    "FAILED_EXTRACTION",
    "FAILED_PERSISTENCE",
    "LIMIT_EXCEEDED",
    "CANCELLED",
}

_DEFAULT_COMMITS_LIMIT = 20
_DEFAULT_ANALYZE_LIMIT = 50
_DEFAULT_COMMIT_ANALYSIS_LIMIT = 10
_DEFAULT_HOTSPOT_THRESHOLD = 5
_DEFAULT_MODEL = "anthropic/claude-haiku-4-5-20251001"


def repository_id_for_url(raw_url: str) -> str:
    try:
        canonical_url = parse_repository_url(raw_url).canonical_url
    except ValueError:
        canonical_url = raw_url
    digest = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:16]
    return f"repo-{digest}"


def _default_commit_query_factory(
    *, project_root: Path, repository_id: str
) -> RepositoryCommitQueryService:
    return build_repository_commit_query_service(project_root=project_root)


def _default_analysis_factory(
    *, project_root: Path, repository_id: str, model: str
) -> RepositoryAnalysisService:
    return build_repository_analysis_service(project_root=project_root, model=model)


def _default_commit_analysis_factory(
    *, project_root: Path, repository_id: str, model: str, sample_model: str | None
) -> "CommitBatchService":
    return build_commit_analysis_service(
        project_root=project_root, model=model, sample_model=sample_model
    )


def _default_pattern_factory(*, project_root: Path, repository_id: str) -> "PatternService":
    return build_pattern_detection_service(project_root=project_root)


def _default_narrative_factory(
    *, project_root: Path, repository_id: str, model: str
) -> "NarrativeGeneratorService":
    return build_narrative_service(project_root=project_root, model=model)


def _default_list_analyses_factory(
    *, project_root: Path, repository_id: str
) -> "AnalysisStoreReader":
    from git_it.repository_ingestion.infrastructure.sqlite import SqliteCommitAnalysisStore
    from git_it.repository_ingestion.infrastructure.workspace import ingestion_workspace_root

    db_path = ingestion_workspace_root(project_root) / "git-it.sqlite3"
    store = SqliteCommitAnalysisStore(db_path)
    store.initialize()
    return store


def main(
    argv: Sequence[str] | None = None,
    *,
    project_root: Path | None = None,
    service_factory: ServiceFactory = build_repository_ingestion_service,
    commit_query_factory: CommitQueryFactory = _default_commit_query_factory,
    analysis_factory: AnalysisFactory = _default_analysis_factory,
    commit_analysis_factory: CommitAnalysisFactory = _default_commit_analysis_factory,
    pattern_factory: PatternFactory = _default_pattern_factory,
    narrative_factory: NarrativeFactory = _default_narrative_factory,
    list_analyses_factory: ListAnalysesFactory = _default_list_analyses_factory,
    budget_confirm_fn: Callable[[int], bool] = _default_budget_confirm,
    budget_threshold: int = _DEFAULT_BUDGET_THRESHOLD,
) -> int:
    parser = argparse.ArgumentParser(prog="git-it")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("repository_url")

    commits_parser = subparsers.add_parser("commits")
    commits_parser.add_argument("repository_url")
    commits_parser.add_argument("--limit", type=int, default=_DEFAULT_COMMITS_LIMIT)
    commits_parser.add_argument(
        "--order",
        choices=["newest", "oldest"],
        default="newest",
        help="Commit order: newest (default) or oldest first",
    )
    commits_parser.add_argument(
        "--since", default=None, metavar="YYYY-MM-DD", help="Include commits from this date onwards"
    )
    commits_parser.add_argument(
        "--until", default=None, metavar="YYYY-MM-DD", help="Include commits up to this date"
    )

    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("repository_url")
    analyze_parser.add_argument("--model", default=_DEFAULT_MODEL)
    analyze_parser.add_argument("--limit", type=int, default=_DEFAULT_ANALYZE_LIMIT)

    analyze_commits_parser = subparsers.add_parser("analyze-commits")
    analyze_commits_parser.add_argument("repository_url")
    analyze_commits_parser.add_argument("--model", default=_DEFAULT_MODEL)
    analyze_commits_parser.add_argument(
        "--sample-model",
        default=None,
        dest="sample_model",
        help="Cheaper model for sample-tier commits (defaults to --model)",
    )
    analyze_commits_parser.add_argument("--limit", type=int, default=_DEFAULT_COMMIT_ANALYSIS_LIMIT)
    analyze_commits_parser.add_argument(
        "--yes", action="store_true", default=False, help="Skip budget confirmation prompt"
    )
    analyze_commits_parser.add_argument(
        "--order",
        choices=["newest", "oldest"],
        default="newest",
        help="Commit order: newest (default) or oldest first",
    )
    analyze_commits_parser.add_argument(
        "--since", default=None, metavar="YYYY-MM-DD", help="Include commits from this date onwards"
    )
    analyze_commits_parser.add_argument(
        "--until", default=None, metavar="YYYY-MM-DD", help="Include commits up to this date"
    )
    analyze_commits_parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Number of parallel LLM calls (default: 1 = sequential)",
    )

    patterns_parser = subparsers.add_parser("patterns")
    patterns_parser.add_argument("repository_url")
    patterns_parser.add_argument(
        "--hotspot-threshold", type=int, default=_DEFAULT_HOTSPOT_THRESHOLD
    )

    case_study_parser = subparsers.add_parser("case-study")
    case_study_parser.add_argument("repository_url")
    case_study_parser.add_argument("--model", default=_DEFAULT_MODEL)
    case_study_parser.add_argument(
        "--force", action="store_true", default=False, help="Regenerate even if cached"
    )

    list_analyses_parser = subparsers.add_parser("list-analyses")
    list_analyses_parser.add_argument("repository_url")
    list_analyses_parser.add_argument("--limit", type=int, default=None)

    run_parser = subparsers.add_parser(
        "run", help="Run full pipeline: ingest + analyze + case study"
    )
    run_parser.add_argument("repository_url")
    run_parser.add_argument("--model", default=_DEFAULT_MODEL)
    run_parser.add_argument(
        "--sample-model",
        default=None,
        dest="sample_model",
        help="Cheaper model for sample-tier commits (defaults to --model)",
    )
    run_parser.add_argument("--limit", type=int, default=_DEFAULT_COMMIT_ANALYSIS_LIMIT)
    run_parser.add_argument(
        "--force", action="store_true", default=False, help="Regenerate case study even if cached"
    )
    run_parser.add_argument(
        "--yes", action="store_true", default=False, help="Skip budget confirmation prompt"
    )
    run_parser.add_argument(
        "--order",
        choices=["newest", "oldest"],
        default="newest",
        help="Commit order: newest (default) or oldest first",
    )
    run_parser.add_argument(
        "--since", default=None, metavar="YYYY-MM-DD", help="Include commits from this date onwards"
    )
    run_parser.add_argument(
        "--until", default=None, metavar="YYYY-MM-DD", help="Include commits up to this date"
    )
    run_parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Number of parallel LLM calls (default: 1 = sequential)",
    )

    args = parser.parse_args(argv)
    resolved_root = Path.cwd() if project_root is None else project_root

    if args.command == "ingest":
        return _run_ingest(
            raw_url=args.repository_url,
            project_root=resolved_root,
            service_factory=service_factory,
        )

    if args.command == "commits":
        return _run_commits(
            raw_url=args.repository_url,
            limit=args.limit,
            order=args.order,
            since=args.since,
            until=args.until,
            project_root=resolved_root,
            commit_query_factory=commit_query_factory,
        )

    if args.command == "analyze":
        return _run_analyze(
            raw_url=args.repository_url,
            model=args.model,
            limit=args.limit,
            project_root=resolved_root,
            analysis_factory=analysis_factory,
        )

    if args.command == "analyze-commits":
        return _run_analyze_commits(
            raw_url=args.repository_url,
            model=args.model,
            sample_model=args.sample_model,
            limit=args.limit,
            yes=args.yes,
            order=args.order,
            since=args.since,
            until=args.until,
            concurrency=args.concurrency,
            project_root=resolved_root,
            commit_analysis_factory=commit_analysis_factory,
            budget_confirm_fn=budget_confirm_fn,
            budget_threshold=budget_threshold,
        )

    if args.command == "patterns":
        return _run_patterns(
            raw_url=args.repository_url,
            hotspot_threshold=args.hotspot_threshold,
            project_root=resolved_root,
            pattern_factory=pattern_factory,
        )

    if args.command == "case-study":
        return _run_case_study(
            raw_url=args.repository_url,
            model=args.model,
            force=args.force,
            project_root=resolved_root,
            narrative_factory=narrative_factory,
        )

    if args.command == "list-analyses":
        return _run_list_analyses(
            raw_url=args.repository_url,
            limit=args.limit,
            project_root=resolved_root,
            list_analyses_factory=list_analyses_factory,
        )

    if args.command == "run":
        return _run_pipeline(
            raw_url=args.repository_url,
            model=args.model,
            sample_model=args.sample_model,
            limit=args.limit,
            force=args.force,
            yes=args.yes,
            order=args.order,
            since=args.since,
            until=args.until,
            concurrency=args.concurrency,
            project_root=resolved_root,
            service_factory=service_factory,
            commit_analysis_factory=commit_analysis_factory,
            narrative_factory=narrative_factory,
            budget_confirm_fn=budget_confirm_fn,
            budget_threshold=budget_threshold,
        )

    parser.error(f"unsupported command: {args.command}")


def _run_pipeline(
    *,
    raw_url: str,
    model: str,
    sample_model: str | None,
    limit: int,
    force: bool,
    yes: bool,
    order: str,
    since: str | None,
    until: str | None,
    concurrency: int,
    project_root: Path,
    service_factory: ServiceFactory,
    commit_analysis_factory: CommitAnalysisFactory,
    narrative_factory: NarrativeFactory,
    budget_confirm_fn: Callable[[int], bool],
    budget_threshold: int,
) -> int:
    import asyncio

    repository_id = repository_id_for_url(raw_url)

    # Step 1: ingest
    print("Ingesting...")
    ingest_service = service_factory(project_root=project_root, repository_id=repository_id)
    ingest_result = ingest_service.ingest(raw_url)
    _print_ingestion_result(ingest_result)
    if ingest_result.status in _FAILED_STATUSES:
        return 1

    # Step 2: analyze commits
    print("Analyzing commits...")
    commit_service = commit_analysis_factory(
        project_root=project_root,
        repository_id=repository_id,
        model=model,
        sample_model=sample_model,
    )
    estimate = commit_service.estimate_llm_calls(
        repository_id, limit=limit, order=order, since=since, until=until
    )
    print(f"  {estimate} commits will be sent to LLM.")
    if estimate > budget_threshold and not yes:
        if not budget_confirm_fn(estimate):
            print("Aborted.")
            return 1
    if concurrency > 1:
        analyses = asyncio.run(
            commit_service.analyze_commits_async(
                repository_id,
                limit=limit,
                order=order,
                since=since,
                until=until,
                concurrency=concurrency,
            )
        )
    else:
        analyses = commit_service.analyze_commits(
            repository_id, limit=limit, order=order, since=since, until=until
        )
    print(f"Analyzed {len(analyses)} commits.")

    # Step 3: generate case study
    print("Generating case study...")
    narrative_service = narrative_factory(
        project_root=project_root, repository_id=repository_id, model=model
    )
    narrative_result = narrative_service.generate(repository_id, force=force)
    _print_narrative(narrative_result)

    return 0


def _run_ingest(
    *,
    raw_url: str,
    project_root: Path,
    service_factory: ServiceFactory,
) -> int:
    service = service_factory(
        project_root=project_root,
        repository_id=repository_id_for_url(raw_url),
    )
    result = service.ingest(raw_url)
    _print_ingestion_result(result)
    return 1 if result.status in _FAILED_STATUSES else 0


def _run_commits(
    *,
    raw_url: str,
    limit: int,
    order: str,
    since: str | None,
    until: str | None,
    project_root: Path,
    commit_query_factory: CommitQueryFactory,
) -> int:
    repository_id = repository_id_for_url(raw_url)
    service = commit_query_factory(project_root=project_root, repository_id=repository_id)
    commits = service.list_commits(
        repository_id, limit=limit, order=order, since=since, until=until
    )
    _print_commits(commits)
    return 0


def _run_analyze(
    *,
    raw_url: str,
    model: str,
    limit: int,
    project_root: Path,
    analysis_factory: AnalysisFactory,
) -> int:
    repository_id = repository_id_for_url(raw_url)
    service = analysis_factory(
        project_root=project_root,
        repository_id=repository_id,
        model=model,
    )
    result = service.analyze(repository_id, limit=limit)
    _print_analysis_result(result)
    return 0


def _run_analyze_commits(
    *,
    raw_url: str,
    model: str,
    sample_model: str | None,
    limit: int,
    yes: bool,
    order: str,
    since: str | None,
    until: str | None,
    concurrency: int,
    project_root: Path,
    commit_analysis_factory: CommitAnalysisFactory,
    budget_confirm_fn: Callable[[int], bool],
    budget_threshold: int,
) -> int:
    import asyncio

    repository_id = repository_id_for_url(raw_url)
    service = commit_analysis_factory(
        project_root=project_root,
        repository_id=repository_id,
        model=model,
        sample_model=sample_model,
    )
    estimate = service.estimate_llm_calls(
        repository_id, limit=limit, order=order, since=since, until=until
    )
    print(f"  {estimate} commits will be sent to LLM.")
    if estimate > budget_threshold and not yes:
        if not budget_confirm_fn(estimate):
            print("Aborted.")
            return 1
    if concurrency > 1:
        analyses = asyncio.run(
            service.analyze_commits_async(
                repository_id,
                limit=limit,
                order=order,
                since=since,
                until=until,
                concurrency=concurrency,
            )
        )
    else:
        analyses = service.analyze_commits(
            repository_id, limit=limit, order=order, since=since, until=until
        )
    _print_commit_analyses(analyses)
    return 0


def _print_commit_analyses(analyses: list[CommitAnalysis]) -> None:
    if not analyses:
        print("No commits stored for this repository. Run 'git-it ingest <url>' first.")
        return
    print(f"Commit Analysis ({len(analyses)} commits)")
    print("=" * 60)
    for analysis in analyses:
        sha_short = analysis.commit_sha[:7]
        risk = analysis.risk_level.value
        confidence_pct = int(analysis.confidence * 100)
        category = analysis.category.value
        print(f"{sha_short}  [{category}]  {analysis.summary}")
        components = (
            ", ".join(analysis.affected_components) if analysis.affected_components else "—"
        )
        print(
            f"         Risk: {risk}  |  Confidence: {confidence_pct}%  |  Components: {components}"
        )
        if analysis.intent:
            inferred = " (inferred)" if analysis.intent_is_inferred else ""
            print(f"         Intent: {analysis.intent}{inferred}")
        if analysis.limitations:
            print(f"         Limitations: {'; '.join(analysis.limitations)}")
        print()


def _run_patterns(
    *,
    raw_url: str,
    hotspot_threshold: int,
    project_root: Path,
    pattern_factory: PatternFactory,
) -> int:
    repository_id = repository_id_for_url(raw_url)
    service = pattern_factory(project_root=project_root, repository_id=repository_id)
    report = service.detect(repository_id, hotspot_threshold=hotspot_threshold)
    _print_pattern_report(report)
    return 0


def _print_pattern_report(report: PatternReport) -> None:
    has_data = (
        report.hotspots
        or report.category_counts
        or report.bugfix_recurrences
        or report.ownership_concentrations
    )
    if not has_data:
        print("No patterns detected. Ingest the repository first, then run 'git-it patterns'.")
        return
    print("Pattern Report")
    print("=" * 60)
    if report.category_counts:
        print("Commit Categories:")
        for cc in report.category_counts:
            print(f"  {cc.category}: {cc.count}")
        print()
    if report.hotspots:
        print(f"Hotspot Files ({len(report.hotspots)} files above threshold):")
        for hotspot in report.hotspots:
            ins = hotspot.total_insertions
            dels = hotspot.total_deletions
            print(
                f"  {hotspot.file_path}  "
                f"(commits: {hotspot.commit_count}, churn: +{ins}/-{dels} = {hotspot.churn})"
            )
        print()
    if report.bugfix_recurrences:
        print("Bugfix-Prone Components:")
        for r in report.bugfix_recurrences:
            print(f"  {r.component}: {r.bugfix_commit_count} bugfix commits")
        print()
    if report.refactor_wave is not None:
        pct = int(report.refactor_wave.refactor_ratio * 100)
        print(
            f"Refactor Wave: {report.refactor_wave.commit_count} refactor commits ({pct}% of total)"
        )
        print()
    if report.revert_signal is not None:
        pct = int(report.revert_signal.revert_ratio * 100)
        print(
            f"Revert Signal: {report.revert_signal.revert_count} revert commits ({pct}% of total)"
        )
        print()
    if report.test_growth_signal is not None:
        sig = report.test_growth_signal
        print(
            f"Test Growth Signal: {sig.test_commit_count} test commits"
            f" vs {sig.bugfix_commit_count} bugfix commits (ratio: {sig.test_to_bugfix_ratio})"
        )
    if report.ownership_concentrations:
        print()
        print("Ownership Concentrations (knowledge silos):")
        for oc in report.ownership_concentrations:
            print(f"  {oc.file_path}  (authors: {oc.author_count}, commits: {oc.commit_count})")


def _run_case_study(
    *,
    raw_url: str,
    model: str,
    force: bool,
    project_root: Path,
    narrative_factory: NarrativeFactory,
) -> int:
    repository_id = repository_id_for_url(raw_url)
    service = narrative_factory(
        project_root=project_root,
        repository_id=repository_id,
        model=model,
    )
    result = service.generate(repository_id, force=force)
    _print_narrative(result)
    return 0


def _run_list_analyses(
    *,
    raw_url: str,
    limit: int | None,
    project_root: Path,
    list_analyses_factory: ListAnalysesFactory,
) -> int:
    repository_id = repository_id_for_url(raw_url)
    store = list_analyses_factory(project_root=project_root, repository_id=repository_id)
    analyses = store.list_analyses(repository_id, limit=limit)
    _print_commit_analyses(analyses)
    return 0


def _print_narrative(result: NarrativeResult) -> None:
    if result.commit_count == 0:
        print("No analyses found. Run 'git-it analyze-commits <url>' first.")
        return
    print(f"Case Study ({result.commit_count} commits, {result.hotspot_count} hotspot files)")
    print("=" * 60)
    print(result.narrative)


def _print_analysis_result(result: AnalysisResult) -> None:
    if result.commit_count == 0:
        print("No commits stored for this repository. Run 'git-it ingest <url>' first.")
        return
    print(f"Analysis ({result.commit_count} commits)")
    print("=" * 60)
    print(result.analysis)


def _print_commits(commits: list[CommitRecord]) -> None:
    if not commits:
        print("No commits stored for this repository. Run 'git-it ingest <url>' first.")
        return
    for commit in commits:
        sha_short = commit.sha[:7]
        date = commit.committed_at[:10]
        message = commit.message.splitlines()[0][:72]
        print(f"{sha_short}  {date}  {message}  ({commit.author_name})")


def _print_ingestion_result(result: IngestionResult) -> None:
    if result.status in _FAILED_STATUSES:
        print(f"Ingestion failed: {result.error_code}")
        if result.run_id is not None:
            print(f"Run ID: {result.run_id}")
        if result.safe_message is not None:
            print(result.safe_message)
        return

    print(f"Ingestion status: {result.status}")
    if result.canonical_url is not None:
        owner_repo = result.canonical_url.removeprefix("https://github.com/")
        print(f"Repository: {owner_repo}")
        print(f"Canonical URL: {result.canonical_url}")
    if result.commits_inserted is not None and result.commits_reused is not None:
        print(f"Commits: {result.commits_inserted} inserted, {result.commits_reused} reused")
    if result.files_inserted is not None and result.files_reused is not None:
        print(f"Files: {result.files_inserted} inserted, {result.files_reused} reused")
    if result.run_id is not None:
        print(f"Run ID: {result.run_id}")
