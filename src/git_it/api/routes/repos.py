import hashlib
import json
import logging
import os
import re
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from git_it.api.auth import require_api_key
from git_it.api.cost import LLM_COST_PER_CALL_USD, estimate_narrative_cost
from git_it.api.deps import get_chat_service, get_project_root
from git_it.api.limiter import limiter
from git_it.api.mappers import map_languages, map_pattern_report
from git_it.api.schemas import (
    MAX_CHAT_HISTORY,
    AnalyzeEstimateResponse,
    AnalyzeRequest,
    AnalyzeResponse,
    AnalyzeStatusResponse,
    CaseStudyResponse,
    ChatRequest,
    ChatResponse,
    CommitsResponse,
    CommitSummaryItem,
    ContributorItem,
    ContributorsResponse,
    DeleteRepoResponse,
    IngestRequest,
    IngestResponse,
    PatternReportResponse,
    RegenerateRequest,
    RegenStatusResponse,
    RepoListResponse,
    RepoSummary,
)
from git_it.chat.service import ChatMessage, ChatService
from git_it.repository_ingestion.application.embedding_service import EmbeddingService
from git_it.repository_ingestion.application.ports import DEFAULT_AUDIENCE
from git_it.repository_ingestion.composition import (
    build_advisory_evidence_store,
    build_advisory_summarizer,
    build_case_study_store,
    build_commit_analysis_service,
    build_commit_count_reader,
    build_commit_with_analysis_reader,
    build_contributor_reader,
    build_default_branch_store,
    build_discussion_evidence_store,
    build_discussion_summarizer,
    build_embedding_client,
    build_embedding_store,
    build_ingestion_run_store,
    build_narrative_service,
    build_release_evidence_store,
    build_release_summarizer,
    build_repo_metadata_store,
    build_repository_deleter,
    build_repository_ingestion_service,
    build_repository_list_reader,
    database_is_provisioned,
)
from git_it.repository_ingestion.domain.url_contract import (
    RepositoryUrlValidationError,
    parse_repository_url,
)
from git_it.repository_ingestion.infrastructure.github import (
    GithubDiscussionsFetcher,
    GithubReleasesFetcher,
    GithubRepoMetadataFetcher,
    GithubSecurityAdvisoriesFetcher,
)
from git_it.repository_ingestion.infrastructure.llm import DEFAULT_MODEL

router = APIRouter(prefix="/api/repos", tags=["repos"])

ProjectRoot = Annotated[Path, Depends(get_project_root)]

_logger = logging.getLogger(__name__)


def _extract_github_username(email: str) -> str | None:
    """Extract a GitHub username from a noreply email address."""
    # New noreply format: 12345678+username@users.noreply.github.com
    m = re.match(r"^\d+\+(.+)@users\.noreply\.github\.com$", email or "")
    if m:
        return m.group(1)
    # Old noreply format: username@users.noreply.github.com
    m = re.match(r"^([^@+]+)@users\.noreply\.github\.com$", email or "")
    if m:
        return m.group(1)
    return None


# In-memory progress store: repository_id → {running, done, total}
_analyze_progress: dict[str, dict] = {}
_analyze_progress_lock = threading.Lock()

_regen_progress: dict[str, dict] = {}
_regen_progress_lock = threading.Lock()


def _canonical_repo_id(canonical_url: str) -> str:
    return "repo-" + hashlib.sha256(canonical_url.encode()).hexdigest()[:12]


def _require_repository_exists(repository_id: str, project_root: Path) -> None:
    """Raise 404 unless ``repository_id`` is a known repository (spec 008 AC).

    A repository is "known" if it has at least one ingestion run recorded —
    the same source of truth ``delete_repo`` already uses to verify a
    repository exists before deleting it. This is backend-aware (honors
    DATABASE_URL) via ``build_ingestion_run_store``.

    A known repository with no analyzed commits or detected patterns yet is
    NOT unknown — callers should only invoke this to gate on existence, then
    let the handler return its normal 200-empty result for real emptiness.
    """
    if not database_is_provisioned(project_root=project_root):
        raise HTTPException(status_code=404, detail="Repository not found.")
    store = build_ingestion_run_store(project_root=project_root)
    runs = store.list_ingestion_runs_for_repository(repository_id)
    if not runs:
        raise HTTPException(status_code=404, detail="Repository not found.")


def _normalize_url(raw: str) -> str:
    raw = raw.strip()
    if re.match(r"^[\w.\-]+/[\w.\-]+$", raw):
        return f"https://github.com/{raw}"
    return raw


def _fetch_and_store_repo_metadata(
    *, repository_id: str, canonical_url: str, project_root: Path
) -> None:
    """Best-effort GitHub stars/languages fetch, run once after a successful ingest.

    Never raises: any failure (no token, non-GitHub URL, HTTP error, malformed
    payload) degrades to "no metadata stored" — the API/UI simply show nothing
    extra for this repository (spec 019).
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return
    try:
        fetcher = GithubRepoMetadataFetcher(token=token)
        metadata = fetcher.fetch_repo_metadata(canonical_url)
        if metadata is None:
            return
        store = build_repo_metadata_store(project_root=project_root)
        store.save_repo_metadata(repository_id, metadata)
    except Exception as e:
        _logger.warning(
            "repo metadata fetch failed: %s",
            type(e).__name__,
            extra={"repository_id": repository_id},
        )


def _fetch_and_store_discussion_evidence(
    *, repository_id: str, canonical_url: str, project_root: Path
) -> None:
    """Best-effort GitHub Discussions fetch + LLM summarize + store, run once after a
    successful ingest. Never raises: any failure degrades to 'no discussion evidence'
    (spec 022). Raw discussion text is used only as summarizer LLM input — only the
    validated DiscussionEvidence is persisted."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return
    try:
        fetcher = GithubDiscussionsFetcher(token=token)
        discussions = fetcher.fetch_qualifying_discussions(canonical_url)
        if not discussions:
            return
        summarizer = build_discussion_summarizer(model=DEFAULT_MODEL)
        evidence = summarizer.summarize(discussions)
        if not evidence:
            return
        store = build_discussion_evidence_store(project_root=project_root)
        store.save_discussion_evidence(repository_id, evidence)

        embedding_client = build_embedding_client()
        if embedding_client is not None:
            embedding_service = EmbeddingService(embedding_client)
            embedding_writer = build_embedding_store(project_root=project_root)
            chunks = [
                chunk
                for item in evidence
                if (chunk := embedding_service.embed_discussion_evidence(repository_id, item))
                is not None
            ]
            if chunks:
                embedding_writer.save_embeddings(repository_id, chunks)
    except Exception as e:
        _logger.warning(
            "discussion evidence fetch failed: %s",
            type(e).__name__,
            extra={"repository_id": repository_id},
        )


def _fetch_and_store_release_evidence(
    *, repository_id: str, canonical_url: str, project_root: Path
) -> None:
    """Best-effort GitHub Releases fetch + LLM summarize + store, run once after a
    successful ingest. Never raises: any failure degrades to 'no release evidence'
    (spec 026). Raw release body text is used only as summarizer LLM input — only the
    validated ReleaseEvidence is persisted. Not embedded (spec 026 non-goal)."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return
    try:
        fetcher = GithubReleasesFetcher(token=token)
        releases = fetcher.fetch_releases(canonical_url)
        if not releases:
            return
        summarizer = build_release_summarizer(model=DEFAULT_MODEL)
        evidence = summarizer.summarize(releases)
        if not evidence:
            return
        store = build_release_evidence_store(project_root=project_root)
        store.save_release_evidence(repository_id, evidence)
    except Exception as e:
        _logger.warning(
            "release evidence fetch failed: %s",
            type(e).__name__,
            extra={"repository_id": repository_id},
        )


def _fetch_and_store_advisory_evidence(
    *, repository_id: str, canonical_url: str, project_root: Path
) -> None:
    """Best-effort GitHub Security Advisories fetch + LLM summarize + store, run once
    after a successful ingest. Never raises: any failure degrades to 'no advisory
    evidence' (spec 026). Raw advisory description text is used only as summarizer LLM
    input — only the validated AdvisoryEvidence is persisted. Not embedded (spec 026
    non-goal)."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return
    try:
        fetcher = GithubSecurityAdvisoriesFetcher(token=token)
        advisories = fetcher.fetch_advisories(canonical_url)
        if not advisories:
            return
        summarizer = build_advisory_summarizer(model=DEFAULT_MODEL)
        evidence = summarizer.summarize(advisories)
        if not evidence:
            return
        store = build_advisory_evidence_store(project_root=project_root)
        store.save_advisory_evidence(repository_id, evidence)
    except Exception as e:
        _logger.warning(
            "advisory evidence fetch failed: %s",
            type(e).__name__,
            extra={"repository_id": repository_id},
        )


def _ingest_bg(url: str, project_root: Path) -> None:
    _logger.info("ingestion started", extra={"url": url})
    try:
        parsed = parse_repository_url(url)
        repository_id = _canonical_repo_id(parsed.canonical_url)
        svc = build_repository_ingestion_service(
            project_root=project_root,
            repository_id=repository_id,
        )
        result = svc.ingest(url)
        _logger.info("ingestion completed", extra={"repository_id": repository_id})
        if result.status == "COMPLETED":
            _fetch_and_store_repo_metadata(
                repository_id=repository_id,
                canonical_url=parsed.canonical_url,
                project_root=project_root,
            )
            _fetch_and_store_discussion_evidence(
                repository_id=repository_id,
                canonical_url=parsed.canonical_url,
                project_root=project_root,
            )
            _fetch_and_store_release_evidence(
                repository_id=repository_id,
                canonical_url=parsed.canonical_url,
                project_root=project_root,
            )
            _fetch_and_store_advisory_evidence(
                repository_id=repository_id,
                canonical_url=parsed.canonical_url,
                project_root=project_root,
            )
    except Exception as e:
        _logger.warning("ingestion failed: %s", type(e).__name__, extra={"url": url})


# ---------------------------------------------------------------------------
# POST /api/repos/ingest
# ---------------------------------------------------------------------------


@router.post("/ingest", response_model=IngestResponse)
@limiter.limit("5/minute")
def ingest_repo(
    request: Request,
    payload: IngestRequest,
    project_root: ProjectRoot,
    _: None = Depends(require_api_key),
) -> IngestResponse:
    url = _normalize_url(payload.url)
    try:
        parsed = parse_repository_url(url)
    except RepositoryUrlValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.error_code) from exc

    repo_id = _canonical_repo_id(parsed.canonical_url)
    t = threading.Thread(target=_ingest_bg, args=(url, project_root), daemon=True)
    t.start()
    return IngestResponse(
        repository_id=repo_id,
        canonical_url=parsed.canonical_url,
        status="INGESTING",
    )


# ---------------------------------------------------------------------------
# GET /api/repos
# ---------------------------------------------------------------------------


@router.get("", response_model=RepoListResponse)
def list_repos(project_root: ProjectRoot) -> RepoListResponse:
    if not database_is_provisioned(project_root=project_root):
        return RepoListResponse(repos=[], total=0)

    reader = build_repository_list_reader(project_root=project_root)
    metadata_store = build_repo_metadata_store(project_root=project_root)
    branch_store = build_default_branch_store(project_root=project_root)
    records = reader.list_repositories()
    repos = []
    for r in records:
        metadata = metadata_store.get_repo_metadata(r.repository_id)
        repos.append(
            RepoSummary(
                repository_id=r.repository_id,
                canonical_url=r.canonical_url,
                status=r.status,
                commit_count=r.commit_count,
                analysis_count=r.analysis_count,
                has_case_study=r.has_case_study,
                stars=metadata.stars if metadata is not None else None,
                languages=map_languages(metadata.languages) if metadata is not None else [],
                default_branch=branch_store.get_default_branch(r.repository_id),
            )
        )
    return RepoListResponse(repos=repos, total=len(repos))


# ---------------------------------------------------------------------------
# GET /api/repos/{repository_id}/case-study
# ---------------------------------------------------------------------------


@router.get("/{repository_id}/case-study", response_model=CaseStudyResponse)
def get_case_study(
    repository_id: str,
    project_root: ProjectRoot,
    audience: str = DEFAULT_AUDIENCE,
) -> CaseStudyResponse:
    if not database_is_provisioned(project_root=project_root):
        raise HTTPException(status_code=404, detail="Case study not found")

    store = build_case_study_store(project_root=project_root)
    record = store.get_case_study(repository_id, audience)

    if record is None:
        raise HTTPException(status_code=404, detail="Case study not found")

    return CaseStudyResponse(
        repository_id=record.repository_id,
        narrative=record.narrative,
        commit_count=record.commit_count,
        hotspot_count=record.hotspot_count,
        generated_at=record.generated_at,
        available_audiences=store.list_available_audiences(repository_id),
    )


def _regen_bg(repository_id: str, audience: str, model: str, project_root: Path) -> None:
    with _regen_progress_lock:
        _regen_progress[repository_id] = {"running": True, "audience": audience, "error": None}
    error_type: str | None = None
    try:
        narrative_svc = build_narrative_service(project_root=project_root, model=model)
        narrative_svc.generate(repository_id, force=True, audience=audience)
    except Exception as e:
        error_type = type(e).__name__
        _logger.warning(
            "case study regen failed: %s", error_type, extra={"repository_id": repository_id}
        )
    finally:
        with _regen_progress_lock:
            _regen_progress[repository_id] = {
                "running": False,
                "audience": audience,
                "error": error_type,
            }


@router.post("/{repository_id}/case-study/regenerate", response_model=RegenStatusResponse)
@limiter.limit("5/minute")
def regenerate_case_study(
    request: Request,
    repository_id: str,
    payload: RegenerateRequest,
    project_root: ProjectRoot,
    _: None = Depends(require_api_key),
) -> RegenStatusResponse:
    if not database_is_provisioned(project_root=project_root):
        raise HTTPException(status_code=404, detail="Repository not found.")
    t = threading.Thread(
        target=_regen_bg,
        args=(repository_id, payload.audience, DEFAULT_MODEL, project_root),
        daemon=True,
    )
    t.start()
    return RegenStatusResponse(running=True, audience=payload.audience)


@router.get("/{repository_id}/case-study/regen-status", response_model=RegenStatusResponse)
def get_regen_status(repository_id: str) -> RegenStatusResponse:
    with _regen_progress_lock:
        state = _regen_progress.get(repository_id, {"running": False, "audience": DEFAULT_AUDIENCE})
    return RegenStatusResponse(
        running=bool(state["running"]),
        audience=str(state["audience"]),
        error=state.get("error"),
    )


# ---------------------------------------------------------------------------
# GET /api/repos/{repository_id}/patterns
# ---------------------------------------------------------------------------


@router.get("/{repository_id}/patterns", response_model=PatternReportResponse)
def get_patterns(
    repository_id: str,
    project_root: ProjectRoot,
    hotspot_threshold: int = 10,
) -> PatternReportResponse:
    from git_it.repository_ingestion.composition import build_pattern_detection_service

    _require_repository_exists(repository_id, project_root)

    service = build_pattern_detection_service(project_root=project_root)
    report = service.detect(repository_id, hotspot_threshold=hotspot_threshold)
    return map_pattern_report(report)


# ---------------------------------------------------------------------------
# GET /api/repos/{repository_id}/commits
# ---------------------------------------------------------------------------


@router.get("/{repository_id}/commits", response_model=CommitsResponse)
def get_commits(
    repository_id: str,
    project_root: ProjectRoot,
    limit: int = 20,
    order: Literal["newest", "oldest"] = "newest",
    category: str | None = None,
) -> CommitsResponse:
    _require_repository_exists(repository_id, project_root)

    reader = build_commit_with_analysis_reader(project_root=project_root)
    total = reader.count_commits_with_analyses(repository_id, category=category)
    records = reader.list_commits_with_analyses(
        repository_id, limit=limit, order=order, category=category
    )

    commits = []
    for record in records:
        cat: str | None = None
        importance: str | None = None
        summary: str | None = None
        summary_beginner: str | None = None
        summary_expert: str | None = None
        affected_components: list[str] = []

        if record.analysis_data is not None:
            try:
                analysis_data = json.loads(record.analysis_data)
                cat = analysis_data.get("category")
                importance = analysis_data.get("risk_level")
                summary = analysis_data.get("summary")
                summary_beginner = analysis_data.get("summary_beginner")
                summary_expert = analysis_data.get("summary_expert")
                raw_ac = analysis_data.get("affected_components") or []
                affected_components = [str(x) for x in raw_ac] if isinstance(raw_ac, list) else []
            except (json.JSONDecodeError, AttributeError):
                pass

        commits.append(
            CommitSummaryItem(
                sha=record.sha,
                message=record.message,
                committed_at=record.committed_at,
                category=cat,
                importance=importance,
                summary=summary,
                summary_beginner=summary_beginner,
                summary_expert=summary_expert,
                affected_components=affected_components,
                files_changed=list(record.files_changed),
            )
        )

    return CommitsResponse(repository_id=repository_id, commits=commits, total=total)


# ---------------------------------------------------------------------------
# POST /api/repos/{repository_id}/analyze
# ---------------------------------------------------------------------------


def _resolve_canonical_url(repository_id: str, project_root: Path) -> str | None:
    """Look up the canonical_url for a repository from the most recent ingestion run."""
    if not database_is_provisioned(project_root=project_root):
        return None
    store = build_ingestion_run_store(project_root=project_root)
    runs = store.list_ingestion_runs_for_repository(repository_id)
    if not runs:
        return None
    return runs[-1].canonical_url


def _analyze_bg(
    repository_id: str, limit: int, model: str, project_root: Path, audience: str = DEFAULT_AUDIENCE
) -> None:
    _logger.info("analysis started", extra={"repository_id": repository_id})
    with _analyze_progress_lock:
        _analyze_progress[repository_id] = {"running": True, "done": 0, "total": 0, "error": None}
    error_type: str | None = None

    def _on_progress(done: int, total: int) -> None:
        with _analyze_progress_lock:
            _analyze_progress[repository_id] = {"running": True, "done": done, "total": total}

    try:
        canonical_url = _resolve_canonical_url(repository_id, project_root)
        svc = build_commit_analysis_service(
            project_root=project_root,
            model=model,
        )
        svc.analyze_commits(
            repository_id,
            limit=None,
            max_new=limit,
            order="oldest",
            on_progress=_on_progress,
            canonical_url=canonical_url,
        )
        _logger.info("analysis completed", extra={"repository_id": repository_id})
        try:
            narrative_svc = build_narrative_service(project_root=project_root, model=model)
            narrative_svc.generate(repository_id, audience=audience)
            _logger.info("case study updated", extra={"repository_id": repository_id})
        except Exception as ne:
            _logger.warning(
                "case study update failed: %s",
                type(ne).__name__,
                extra={"repository_id": repository_id},
            )
    except Exception as e:
        error_type = type(e).__name__
        _logger.warning("analysis failed: %s", error_type, extra={"repository_id": repository_id})
    finally:
        with _analyze_progress_lock:
            prev = _analyze_progress.get(repository_id, {})
            _analyze_progress[repository_id] = {
                "running": False,
                "done": prev.get("done", 0),
                "total": prev.get("total", 0),
                "error": error_type,
            }


@router.get("/{repository_id}/analyze/estimate", response_model=AnalyzeEstimateResponse)
@limiter.limit("20/minute")
def estimate_analyze(
    request: Request,
    repository_id: str,
    project_root: ProjectRoot,
    limit: int = 20,
    model: str = DEFAULT_MODEL,
) -> AnalyzeEstimateResponse:
    _require_repository_exists(repository_id, project_root)
    count_reader = build_commit_count_reader(project_root=project_root)
    total_commits = count_reader.count_commits(repository_id)
    analyzed_commits = count_reader.count_analyses(repository_id)
    svc = build_commit_analysis_service(project_root=project_root, model=model)
    estimated_llm_calls = svc.estimate_llm_calls(repository_id, limit=limit, order="newest")
    estimated_analysis_cost = round(estimated_llm_calls * LLM_COST_PER_CALL_USD, 4)
    estimated_narrative_cost = estimate_narrative_cost(total_commits)
    return AnalyzeEstimateResponse(
        total_commits=total_commits,
        analyzed_commits=analyzed_commits,
        unanalyzed_commits=max(0, total_commits - analyzed_commits),
        estimated_llm_calls=estimated_llm_calls,
        estimated_analysis_cost_usd=estimated_analysis_cost,
        estimated_narrative_cost_usd=estimated_narrative_cost,
        estimated_cost_usd=round(estimated_analysis_cost + estimated_narrative_cost, 4),
    )


@router.post("/{repository_id}/analyze", response_model=AnalyzeResponse)
@limiter.limit("10/minute")
def trigger_analyze(
    request: Request,
    repository_id: str,
    payload: AnalyzeRequest,
    project_root: ProjectRoot,
    _: None = Depends(require_api_key),
) -> AnalyzeResponse:
    if not database_is_provisioned(project_root=project_root):
        raise HTTPException(status_code=404, detail="Repository not found.")
    t = threading.Thread(
        target=_analyze_bg,
        args=(repository_id, payload.limit, payload.model, project_root, payload.audience),
        daemon=True,
    )
    t.start()
    return AnalyzeResponse(status="ANALYZING", limit=payload.limit)


@router.get("/{repository_id}/analyze/status", response_model=AnalyzeStatusResponse)
def get_analyze_status(repository_id: str) -> AnalyzeStatusResponse:
    with _analyze_progress_lock:
        p = _analyze_progress.get(repository_id)
    if p is None:
        return AnalyzeStatusResponse(running=False, done=0, total=0, pct=0)
    total = p["total"]
    done = p["done"]
    pct = round(done / total * 100) if total > 0 else 0
    return AnalyzeStatusResponse(
        running=p["running"], done=done, total=total, pct=pct, error=p.get("error")
    )


# ---------------------------------------------------------------------------
# GET /api/repos/{repository_id}/contributors
# ---------------------------------------------------------------------------


@router.get("/{repository_id}/contributors", response_model=ContributorsResponse)
def get_contributors(repository_id: str, project_root: ProjectRoot) -> ContributorsResponse:
    if not database_is_provisioned(project_root=project_root):
        raise HTTPException(status_code=404, detail="Repository not found.")

    reader = build_contributor_reader(project_root=project_root)
    records = reader.list_contributors(repository_id)

    if not records:
        raise HTTPException(status_code=404, detail="No commits found for this repository.")

    contributors = [
        ContributorItem(
            author_name=r.author_name,
            commit_count=r.commit_count,
            first_commit=r.first_commit,
            last_commit=r.last_commit,
            is_bot=r.is_bot,
            active_days=r.active_days,
            category_counts=r.category_counts,
            top_files=r.top_files,
            github_username=r.github_username,
        )
        for r in records
    ]

    return ContributorsResponse(
        repository_id=repository_id,
        contributors=contributors,
        total=len(contributors),
    )


# ---------------------------------------------------------------------------
# POST /api/repos/{repository_id}/chat  (GitItGPT — spec 012)
# ---------------------------------------------------------------------------


@router.post("/{repository_id}/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
def chat_with_repo(
    request: Request,
    repository_id: str,
    payload: ChatRequest,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    _: None = Depends(require_api_key),
) -> ChatResponse:
    # Bound prompt size / budget: keep only the most recent turns.
    history = [
        ChatMessage(role=t.role, content=t.content) for t in payload.history[-MAX_CHAT_HISTORY:]
    ]
    try:
        result = chat_service.chat(
            repository_id=repository_id,
            message=payload.message,
            history=history,
        )
    except Exception as exc:
        # Never leak the raw error (may carry provider keys or internals).
        _logger.warning(
            "chat failed: %s", type(exc).__name__, extra={"repository_id": repository_id}
        )
        raise HTTPException(
            status_code=503, detail="The assistant is temporarily unavailable."
        ) from exc
    return ChatResponse(reply=result.reply)


# ---------------------------------------------------------------------------
# POST /api/repos/{repository_id}/chat/stream  (GitItGPT streaming — spec 013)
# ---------------------------------------------------------------------------


def _sse_data(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _sse_event(event: str, payload: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@router.post("/{repository_id}/chat/stream")
@limiter.limit("20/minute")
def chat_stream_with_repo(
    request: Request,
    repository_id: str,
    payload: ChatRequest,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    _: None = Depends(require_api_key),
) -> StreamingResponse:
    # Bound prompt size / budget: keep only the most recent turns.
    history = [
        ChatMessage(role=t.role, content=t.content) for t in payload.history[-MAX_CHAT_HISTORY:]
    ]

    def _generate() -> Iterator[str]:
        try:
            for delta in chat_service.chat_stream(
                repository_id=repository_id,
                message=payload.message,
                history=history,
            ):
                yield _sse_data({"text_delta": delta})
            yield _sse_event("done", {})
        except Exception as exc:
            # Status/headers are already committed once streaming starts — a
            # mid-stream failure can only be signalled inside the stream, and
            # never with the raw exception (may carry provider keys/internals).
            _logger.warning(
                "chat stream failed: %s", type(exc).__name__, extra={"repository_id": repository_id}
            )
            yield _sse_event("error", {"message": "The assistant is temporarily unavailable."})

    return StreamingResponse(_generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# DELETE /api/repos/{repository_id}
# ---------------------------------------------------------------------------


@router.delete("/{repository_id}", response_model=DeleteRepoResponse)
@limiter.limit("10/minute")
def delete_repo(
    request: Request,
    repository_id: str,
    project_root: ProjectRoot,
    _: None = Depends(require_api_key),
) -> DeleteRepoResponse:
    _require_repository_exists(repository_id, project_root)

    # Block deletion while an analysis is in progress
    with _analyze_progress_lock:
        analyze_state = _analyze_progress.get(repository_id)
    if analyze_state and analyze_state.get("running"):
        raise HTTPException(
            status_code=409,
            detail="Cannot delete repository while an operation is in progress.",
        )

    # Block deletion while a case-study regeneration is in progress
    with _regen_progress_lock:
        regen_state = _regen_progress.get(repository_id)
    if regen_state and regen_state.get("running"):
        raise HTTPException(
            status_code=409,
            detail="Cannot delete repository while an operation is in progress.",
        )

    deleter = build_repository_deleter(project_root=project_root)
    deleter.delete_repository(repository_id)

    return DeleteRepoResponse(deleted=True, repository_id=repository_id)
