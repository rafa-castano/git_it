"""
Git It — Semantic Search Eval

Measures whether embedding-based semantic search (spec 023) satisfies the three
properties the spec's "Evaluation required" section demands:

1. Concept-recall — a natural-language query, phrased with *different words*
   than a fixture summary's own vocabulary, still surfaces the matching
   commit/discussion within the top-k results.
2. No raw-text leakage in results — none of the fixture's raw (hypothetical)
   commit-message text appears in any `SimilarityResult.summary_text`; only the
   validated summary is ever surfaced (deterministic check, mirrors spec 022's
   eval).
3. Relevance ordering sanity — a query closely matching one summary's wording
   scores higher than a query about an unrelated concept, over the same
   fixture set. A coarse sanity check on the embedding model's usefulness for
   this corpus, not a strict correctness proof.

Unlike `evals/discussion_evidence_eval.py` (which drives a completions model),
this eval's real dependency is `OPENAI_API_KEY` specifically — it calls
`LiteLLMEmbeddingClient`/`build_embedding_client()` for embeddings, never a
completions model, so there is no `--model` argument here.

Usage:
    uv run python evals/semantic_search_eval.py [--verbose]
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

# ---------------------------------------------------------------------------
# Bootstrap: ensure the project src is importable when run from the repo root.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

if TYPE_CHECKING:
    from git_it.repository_ingestion.domain.embeddings import EmbeddedChunk

# Raw (hypothetical) commit-message sentinel text — must NEVER appear in any
# SimilarityResult.summary_text. Only the validated CommitAnalysis.summary
# fixtures below (which paraphrase these) may ever be embedded/surfaced.
_SENTINEL_SQLI = "ZEBRA-QUUX-SENTINEL raw string concatenation in the login SQL query"
_SENTINEL_FLAKY = "PLATYPUS-FOXTROT-SENTINEL sleep(5) hack to unblock the flaky test job"
_SENTINEL_MIGRATION = "WOMBAT-YANKEE-SENTINEL rolled back the botched users table migration"
_SENTINEL_AUTH = "IGUANA-TANGO-SENTINEL token never expired due to a missing exp claim check"
_SENTINEL_DOCS = "PELICAN-OSCAR-SENTINEL fixed a typo in the README installation section"


def _check_api_key() -> bool:
    """Return True if OPENAI_API_KEY is present.

    Unlike `discussion_evidence_eval.py`'s `_check_api_key`, this eval has a
    single, fixed real dependency — `LiteLLMEmbeddingClient`/
    `build_embedding_client()` always requires `OPENAI_API_KEY` specifically,
    regardless of whichever provider serves completions elsewhere in this
    project. There is no `--model` argument to inspect here.
    """
    return bool(os.environ.get("OPENAI_API_KEY"))


# ---------------------------------------------------------------------------
# Fixture: CommitAnalysis summaries covering distinct, clearly-separated
# concepts, plus natural-language queries phrased with different vocabulary
# than the summaries themselves use.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FixtureItem:
    source_id: str
    summary: str
    raw_sentinel: str


def _build_fixture_items() -> list[_FixtureItem]:
    return [
        _FixtureItem(
            source_id="a1a1a1a1a1a1",
            summary=(
                "Fixed a SQL injection vulnerability in the login form by switching to "
                "parameterized queries instead of building SQL from raw string concatenation."
            ),
            raw_sentinel=_SENTINEL_SQLI,
        ),
        _FixtureItem(
            source_id="b2b2b2b2b2b2",
            summary=(
                "Stabilized a flaky test suite by removing a timing-dependent sleep hack "
                "and replacing it with a deterministic wait condition."
            ),
            raw_sentinel=_SENTINEL_FLAKY,
        ),
        _FixtureItem(
            source_id="c3c3c3c3c3c3",
            summary=(
                "Rolled back a database migration that had corrupted the users table "
                "schema, restoring the previous column definitions."
            ),
            raw_sentinel=_SENTINEL_MIGRATION,
        ),
        _FixtureItem(
            source_id="d4d4d4d4d4d4",
            summary=(
                "Fixed a bug where authentication tokens never expired because the "
                "expiry claim was never checked during validation."
            ),
            raw_sentinel=_SENTINEL_AUTH,
        ),
        _FixtureItem(
            source_id="e5e5e5e5e5e5",
            summary="Corrected a spelling mistake in the README's installation instructions.",
            raw_sentinel=_SENTINEL_DOCS,
        ),
    ]


# Natural-language queries, deliberately worded differently than the summary
# text above, mapped to the fixture item that is the known-correct match.
_QUERIES: list[tuple[str, str]] = [
    ("what security mistakes were made early in the project", "a1a1a1a1a1a1"),
    ("find commits about unreliable or intermittently failing tests", "b2b2b2b2b2b2"),
    ("did we ever have to undo a bad schema change", "c3c3c3c3c3c3"),
    ("was there ever a problem with sessions or logins never expiring", "d4d4d4d4d4d4"),
]

# A query about a concept clearly unrelated to the SQL-injection fixture item,
# used for the relevance-ordering sanity check (query 0 above, "security
# mistakes", should score higher against the SQL-injection summary than this
# control query about documentation typos does).
_CONTROL_QUERY = "was there ever a typo fixed in project documentation"


# ---------------------------------------------------------------------------
# In-memory EmbeddingReader stand-in — satisfies the EmbeddingReader Protocol
# without touching a real database.
# ---------------------------------------------------------------------------


class _InMemoryEmbeddingReader:
    def __init__(self, chunks: list[EmbeddedChunk]) -> None:
        self._chunks = chunks

    def get_all_embeddings(self, repository_id: str) -> list[EmbeddedChunk]:
        return list(self._chunks)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    name: str
    passed: bool
    details: str


def _check_concept_recall(
    service: object,
    repository_id: str,
    top_k: int,
) -> CheckResult:
    """For each query, assert the known-correct fixture appears within top-k."""
    from git_it.repository_ingestion.application.semantic_search_service import (
        SemanticSearchService,
    )

    assert isinstance(service, SemanticSearchService)  # narrow for mypy/readability

    misses: list[str] = []
    for query, expected_source_id in _QUERIES:
        results = service.search(repository_id, query, top_k=top_k)
        found = any(r.evidence_ref == expected_source_id for r in results)
        if not found:
            misses.append(f"query={query!r} expected={expected_source_id!r}")

    passed = not misses
    details = (
        f"All {len(_QUERIES)} queries recalled their known-correct commit within top-{top_k}."
        if passed
        else f"Missed recall for: {misses}"
    )
    return CheckResult(name="concept_recall", passed=passed, details=details)


def _check_no_raw_text_leakage(
    all_results: list[object],
    fixture_items: list[_FixtureItem],
) -> CheckResult:
    """Deterministic check: no raw sentinel commit-message text may appear in
    any SimilarityResult.summary_text — only the validated summary is ever
    surfaced (mirrors spec 022's eval)."""
    leaked: list[str] = []
    for result in all_results:
        summary_text = getattr(result, "summary_text", "")
        for item in fixture_items:
            if item.raw_sentinel in summary_text:
                leaked.append(f"{item.source_id}: sentinel found in summary_text")

    passed = not leaked
    details = (
        "No raw commit-message sentinel text found in any SimilarityResult.summary_text."
        if passed
        else f"Raw text leaked into results: {leaked}"
    )
    return CheckResult(name="no_raw_text_leakage", passed=passed, details=details)


def _check_relevance_ordering(
    service: object,
    repository_id: str,
) -> CheckResult:
    """A query closely matching one summary's wording should score higher for
    that summary than a query about a clearly unrelated concept does — a
    coarse sanity check, not a strict correctness proof."""
    from git_it.repository_ingestion.application.semantic_search_service import (
        SemanticSearchService,
    )

    assert isinstance(service, SemanticSearchService)

    matching_query, target_source_id = _QUERIES[0]  # security-mistakes query, SQLi fixture
    matching_results = service.search(repository_id, matching_query, top_k=len(_QUERIES) + 1)
    control_results = service.search(repository_id, _CONTROL_QUERY, top_k=len(_QUERIES) + 1)

    matching_score = next(
        (r.score for r in matching_results if r.evidence_ref == target_source_id), None
    )
    control_score = next(
        (r.score for r in control_results if r.evidence_ref == target_source_id), None
    )

    if matching_score is None or control_score is None:
        return CheckResult(
            name="relevance_ordering_sanity",
            passed=False,
            details=(
                f"Could not find target commit {target_source_id!r} in one of the result "
                "sets used for this comparison."
            ),
        )

    passed = matching_score > control_score
    details = (
        f"matching query score={matching_score:.4f} > control query score={control_score:.4f}"
        if passed
        else (
            f"matching query score={matching_score:.4f} did NOT exceed "
            f"control query score={control_score:.4f}"
        )
    )
    return CheckResult(name="relevance_ordering_sanity", passed=passed, details=details)


# ---------------------------------------------------------------------------
# Report printing
# ---------------------------------------------------------------------------


def _print_report(
    model: str, results: list[CheckResult], all_similarity_results: list[object], verbose: bool
) -> bool:
    """Print the report and return True iff all checks passed (all three
    checks in this eval are deterministic per spec 023, unlike spec 022's
    eval which also reports one qualitative-only check)."""
    print()
    print("=" * 60)
    print("Git It — Semantic Search Eval Report")
    print("=" * 60)
    print(f"Embedding model: {model}")
    print()

    all_passed = True
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        print(f"[{mark}] {r.name}")
        print(f"       {r.details}")
        if not r.passed:
            all_passed = False
    print()

    if verbose:
        print("-" * 60)
        print("Similarity results:")
        print("-" * 60)
        for similarity_result in all_similarity_results:
            print(similarity_result)
        print()

    verdict = "PASS" if all_passed else "FAIL"
    print(f"Verdict: {verdict}")
    print("=" * 60)
    print()
    return all_passed


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Git It — semantic search eval (spec 023)")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print every similarity result gathered during the eval",
    )
    args = parser.parse_args()

    if not _check_api_key():
        print(
            "Skipped — OPENAI_API_KEY is not set. This eval requires a real embedding "
            "API call (LiteLLMEmbeddingClient) and is not part of the deterministic "
            "unit suite.",
        )
        sys.exit(0)

    from git_it.repository_ingestion.application.semantic_search_service import (
        SemanticSearchService,
    )
    from git_it.repository_ingestion.domain.embeddings import EmbeddedChunk
    from git_it.repository_ingestion.infrastructure.llm import (
        EMBEDDING_MODEL,
        LiteLLMEmbeddingClient,
    )

    repository_id = "eval-harness-repo"
    fixture_items = _build_fixture_items()
    embedding_client = LiteLLMEmbeddingClient()

    print(f"Running semantic search eval: embedding model={EMBEDDING_MODEL}")
    print(f"Embedding {len(fixture_items)} fixture summaries...")

    now = datetime.now(UTC)
    try:
        chunks = [
            EmbeddedChunk(
                repository_id=repository_id,
                source_type="commit_analysis",
                source_id=item.source_id,
                text=item.summary,
                vector=embedding_client.embed(item.summary),
                model=EMBEDDING_MODEL,
                created_at=now,
            )
            for item in fixture_items
        ]
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"Error during embedding: {exc}", file=sys.stderr)
        raise

    reader = _InMemoryEmbeddingReader(chunks)
    service = SemanticSearchService(embedding_client, reader)

    top_k = 3
    all_results: list[object] = []
    for query, _expected in _QUERIES:
        all_results.extend(service.search(repository_id, query, top_k=top_k))
    all_results.extend(service.search(repository_id, _CONTROL_QUERY, top_k=top_k))

    checks = [
        _check_concept_recall(service, repository_id, top_k),
        _check_no_raw_text_leakage(all_results, fixture_items),
        _check_relevance_ordering(service, repository_id),
    ]

    all_passed = _print_report(EMBEDDING_MODEL, checks, all_results, args.verbose)

    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
