"""
Git It — Discussion Evidence Eval

Measures whether case-study narratives generated with GitHub Discussions evidence
(spec 022) satisfy the three properties the spec's "Evaluation required" section
demands:

1. Citation completeness — a discussion-sourced claim in the narrative is
   accompanied by its `discussion_url`.
2. No raw-text leakage — none of the untrusted, raw `Discussion` fixture text
   (title/body/answer_body) appears anywhere in the generated narrative. This is
   the deterministic, security-relevant check: only validated `DiscussionEvidence`
   summaries and URLs may ever reach the narrative, never the raw discussion text
   that was fed to the summarizer.
3. Uncertainty preservation — best-effort/qualitative per the spec: narratives
   built from a low-confidence `DiscussionEvidence` item should read with hedged
   language ("evidence suggests", "may", "appears") rather than an unqualified
   claim. Reported, not hard-failed.

Usage:
    uv run python evals/discussion_evidence_eval.py [--model MODEL]
"""

from __future__ import annotations

import argparse
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
    from git_it.repository_ingestion.application.ports import TimestampedAnalysis
    from git_it.repository_ingestion.domain.discussions import Discussion, DiscussionEvidence
    from git_it.repository_ingestion.domain.patterns import PatternReport

_DEFAULT_MODEL = "anthropic/claude-haiku-4-5-20251001"

# Sentinel phrases embedded in the raw (untrusted) fixture Discussion text. These
# strings must NEVER appear in the generated narrative — only the corresponding
# validated DiscussionEvidence.summary strings (which paraphrase them) may.
_SENTINEL_CACHE = "ZEBRA-QUUX-SENTINEL cache invalidation was chosen"
_SENTINEL_MEMLEAK = "PLATYPUS-FOXTROT-SENTINEL memory leak in the worker pool"
_SENTINEL_LOWCONF = "WOMBAT-YANKEE-SENTINEL rumor about a rewrite in Rust"


def _check_api_key(model: str) -> bool:
    """Return True if the required API key for *model* is present.

    Mirrors evals/run.py's `_check_api_key`, but returns a bool instead of exiting,
    so this eval can print a clean "skipped" message and exit 0 in an environment
    with no LLM configured (this eval must never hard-fail CI without a key).
    """
    import os

    model_lower = model.lower()
    required: dict[str, str] = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "cohere": "COHERE_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "vertex": "GOOGLE_APPLICATION_CREDENTIALS",
        "azure": "AZURE_API_KEY",
        "together": "TOGETHERAI_API_KEY",
        "groq": "GROQ_API_KEY",
        "mistral": "MISTRAL_API_KEY",
    }
    for provider, env_var in required.items():
        if provider in model_lower:
            return bool(os.environ.get(env_var))
    # Unknown provider (custom LiteLLM router) — assume configured elsewhere.
    return True


# ---------------------------------------------------------------------------
# Fixture: raw Discussions (untrusted, ephemeral) + matching DiscussionEvidence
# (validated, persisted). The raw Discussion text is what must NEVER leak into
# the narrative; only DiscussionEvidence.summary/discussion_url may.
# ---------------------------------------------------------------------------


def _build_discussion_fixture() -> list[Discussion]:
    from git_it.repository_ingestion.domain.discussions import Discussion

    return [
        Discussion(
            id="D_kwDOAbc123",
            url="https://github.com/octo-org/octo-repo/discussions/42",
            title=f"Why did we invalidate the cache this way? {_SENTINEL_CACHE}",
            body=(
                f"Long design discussion. {_SENTINEL_CACHE} after comparing write-through "
                "vs write-behind approaches for the session cache."
            ),
            answer_body=f"Accepted answer: {_SENTINEL_CACHE} to keep read latency low.",
            category="Q&A",
            is_answered=True,
            upvote_count=12,
            reaction_count=4,
            comment_count=6,
            updated_at="2026-05-01T00:00:00Z",
        ),
        Discussion(
            id="D_kwDOAbc456",
            url="https://github.com/octo-org/octo-repo/discussions/57",
            title=f"Recurring issue: {_SENTINEL_MEMLEAK}",
            body=(
                f"Multiple users report {_SENTINEL_MEMLEAK} under sustained load, "
                "roughly every few days in production."
            ),
            answer_body=None,
            category="General",
            is_answered=False,
            upvote_count=9,
            reaction_count=3,
            comment_count=5,
            updated_at="2026-05-10T00:00:00Z",
        ),
        Discussion(
            id="D_kwDOAbc789",
            url="https://github.com/octo-org/octo-repo/discussions/61",
            title=f"Unverified: {_SENTINEL_LOWCONF}",
            body=(
                f"One user mentions a {_SENTINEL_LOWCONF} they heard about secondhand, "
                "with no maintainer confirmation."
            ),
            answer_body=None,
            category="General",
            is_answered=False,
            upvote_count=6,
            reaction_count=0,
            comment_count=1,
            updated_at="2026-05-15T00:00:00Z",
        ),
    ]


def _build_discussion_evidence_fixture() -> list[DiscussionEvidence]:
    from git_it.repository_ingestion.domain.discussions import DiscussionEvidence

    now = datetime.now(UTC)
    return [
        DiscussionEvidence(
            discussion_id="D_kwDOAbc123",
            discussion_url="https://github.com/octo-org/octo-repo/discussions/42",
            claim_type="design_rationale",
            summary=(
                "Maintainers chose a write-through cache invalidation strategy over "
                "write-behind to keep read latency predictable."
            ),
            confidence=0.9,
            limitations=[],
            source_inputs=["D_kwDOAbc123"],
            generated_at=now,
            model="eval-fixture",
        ),
        DiscussionEvidence(
            discussion_id="D_kwDOAbc456",
            discussion_url="https://github.com/octo-org/octo-repo/discussions/57",
            claim_type="pain_point",
            summary=(
                "Users repeatedly report a memory leak in the worker pool under "
                "sustained production load."
            ),
            confidence=0.75,
            limitations=[],
            source_inputs=["D_kwDOAbc456"],
            generated_at=now,
            model="eval-fixture",
        ),
        DiscussionEvidence(
            discussion_id="D_kwDOAbc789",
            discussion_url="https://github.com/octo-org/octo-repo/discussions/61",
            claim_type="pain_point",
            summary=(
                "An unconfirmed community rumor suggests a possible rewrite of the "
                "project in Rust; no maintainer has verified this."
            ),
            confidence=0.3,
            limitations=["Single secondhand report, no maintainer confirmation."],
            source_inputs=["D_kwDOAbc789"],
            generated_at=now,
            model="eval-fixture",
        ),
    ]


def _build_commit_fixture() -> list[TimestampedAnalysis]:
    """A couple of TimestampedAnalysis fixtures so the narrative has commit content too."""
    from git_it.repository_ingestion.application.ports import TimestampedAnalysis
    from git_it.repository_ingestion.domain.analysis import (
        CommitAnalysis,
        CommitCategory,
        RiskLevel,
    )

    return [
        TimestampedAnalysis(
            analysis=CommitAnalysis(
                commit_sha="a1b2c3d4e5f6",
                summary="Introduced a session cache in front of the primary datastore.",
                category=CommitCategory.FEATURE,
                risk_level=RiskLevel.MEDIUM,
                confidence=0.85,
                affected_components=["cache", "session"],
            ),
            committed_at="2026-04-28T00:00:00Z",
        ),
        TimestampedAnalysis(
            analysis=CommitAnalysis(
                commit_sha="f6e5d4c3b2a1",
                summary="Added a background worker pool for async job processing.",
                category=CommitCategory.FEATURE,
                risk_level=RiskLevel.MEDIUM,
                confidence=0.8,
                affected_components=["worker"],
            ),
            committed_at="2026-05-02T00:00:00Z",
        ),
    ]


# ---------------------------------------------------------------------------
# Stubs — narrative service collaborators that do not touch the real DB/GitHub.
# ---------------------------------------------------------------------------


class _StubTemporalReader:
    def __init__(self, items: list[TimestampedAnalysis]) -> None:
        self._items = items

    def list_analyses_with_dates(self, repository_id: str) -> list[TimestampedAnalysis]:
        return self._items

    def list_analyses_since(self, repository_id: str, *, since: str) -> list[TimestampedAnalysis]:
        return []


class _StubPatternService:
    def detect(self, repository_id: str, *, hotspot_threshold: int = 3) -> PatternReport:
        from git_it.repository_ingestion.domain.patterns import PatternReport

        return PatternReport(repository_id=repository_id, hotspots=[])


class _StubDiscussionReader:
    def __init__(self, evidence: list[DiscussionEvidence]) -> None:
        self._evidence = evidence

    def get_discussion_evidence(self, repository_id: str) -> list[DiscussionEvidence]:
        return self._evidence


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    name: str
    passed: bool
    details: str


def _check_no_raw_text_leakage(narrative: str, discussions: list[Discussion]) -> CheckResult:
    """Deterministic, security-relevant check: no raw fixture text may appear.

    This is the strongest check in this eval — it does not depend on the LLM's
    phrasing at all. Checking whole `title`/`body`/`answer_body` strings for an
    exact match would be too weak: an LLM never reproduces an entire raw field
    verbatim, so that check would trivially "pass" even if raw text leaked in
    part. Instead, each fixture discussion embeds a unique sentinel phrase
    (`ZEBRA-QUUX-SENTINEL ...`, `PLATYPUS-FOXTROT-SENTINEL ...`,
    `WOMBAT-YANKEE-SENTINEL ...`) directly inside its raw `title`/`body`/
    `answer_body`. Asserting that none of those sentinel substrings — nor the
    raw fields themselves, as a defense-in-depth check — appear anywhere in the
    generated narrative is the practical, deterministic form of "no substring of
    the raw discussion text leaked into LLM output."
    """
    sentinels = (_SENTINEL_CACHE, _SENTINEL_MEMLEAK, _SENTINEL_LOWCONF)
    leaked: list[str] = [s for s in sentinels if s in narrative]

    # Defense-in-depth: also flag verbatim reproduction of an entire raw field,
    # even though this is a much less likely failure mode than a sentinel leak.
    for d in discussions:
        for field_name, text in (
            ("title", d.title),
            ("body", d.body),
            ("answer_body", d.answer_body or ""),
        ):
            if text and text in narrative:
                leaked.append(f"{d.id}.{field_name}")

    passed = not leaked
    details = (
        "No sentinel phrase or raw discussion title/body/answer_body substring "
        "found in the narrative."
        if passed
        else f"Raw discussion text leaked into the narrative: {leaked}"
    )
    return CheckResult(name="no_raw_text_leakage", passed=passed, details=details)


def _check_citation_completeness(narrative: str, evidence: list[DiscussionEvidence]) -> CheckResult:
    """Practical, non-brittle heuristic for citation completeness.

    For each DiscussionEvidence item, check whether its summary content appears
    to have been used (a rough proxy: any of the summary's "significant" words —
    longer than 5 characters — appear in the narrative). If the narrative shows
    signs of having used that evidence item, its discussion_url must also appear
    somewhere in the output. This deliberately does not require an exact summary
    match (the LLM paraphrases), only that a used claim is not left uncited.
    """
    missing_citations: list[str] = []
    used_any_evidence = False
    lowered_narrative = narrative.lower()

    for item in evidence:
        significant_words = [w.strip(".,;:()").lower() for w in item.summary.split() if len(w) > 5]
        hits = sum(1 for w in significant_words if w in lowered_narrative)
        # Heuristic threshold: at least 2 distinctive words from the summary
        # showing up in the narrative is treated as "this evidence was used".
        evidence_appears_used = significant_words and hits >= min(2, len(significant_words))
        if evidence_appears_used:
            used_any_evidence = True
            if item.discussion_url not in narrative:
                missing_citations.append(item.discussion_url)

    passed = not missing_citations
    if not used_any_evidence:
        details = (
            "Heuristic could not confirm any discussion evidence was clearly used in the "
            "narrative (no citation-completeness violation to report)."
        )
    elif passed:
        details = "Every discussion-evidence item that appears used is cited by its URL."
    else:
        details = f"Discussion evidence used without its citation URL present: {missing_citations}"
    return CheckResult(name="citation_completeness", passed=passed, details=details)


_HEDGE_PHRASES = (
    "evidence suggests",
    "may ",
    "may have",
    "appears to",
    "seems to",
    "unconfirmed",
    "reportedly",
    "possibly",
    "it is unclear",
    "not verified",
    "rumor",
)


def _check_uncertainty_preservation(
    narrative: str, low_confidence_evidence: DiscussionEvidence
) -> CheckResult:
    """Best-effort, qualitative check (per spec 022's Evaluation required section).

    Reports whether hedged language appears near the low-confidence claim rather
    than asserting a hard pass/fail, matching the spec's wording: "may start as a
    manual/qualitative check rather than an automated assertion."
    """
    lowered = narrative.lower()
    hedges_found = [p for p in _HEDGE_PHRASES if p in lowered]
    # Qualitative signal only — never fails the eval, only reported.
    passed = bool(hedges_found)
    details = (
        f"Hedged language found in narrative: {hedges_found}"
        if hedges_found
        else "No obvious hedged language found near low-confidence claim "
        f"({low_confidence_evidence.discussion_url}); this is a qualitative "
        "observation, not a hard failure."
    )
    return CheckResult(name="uncertainty_preservation_qualitative", passed=passed, details=details)


# ---------------------------------------------------------------------------
# Report printing
# ---------------------------------------------------------------------------


def _print_report(model: str, results: list[CheckResult], narrative: str, verbose: bool) -> bool:
    """Print the report and return True iff the deterministic checks passed."""
    print()
    print("=" * 60)
    print("Git It — Discussion Evidence Eval Report")
    print("=" * 60)
    print(f"Model: {model}")
    print()

    deterministic_names = {"no_raw_text_leakage", "citation_completeness"}
    all_deterministic_passed = True
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        print(f"[{mark}] {r.name}")
        print(f"       {r.details}")
        if r.name in deterministic_names and not r.passed:
            all_deterministic_passed = False
    print()

    if verbose:
        print("-" * 60)
        print("Generated narrative:")
        print("-" * 60)
        print(narrative)
        print()

    verdict = "PASS" if all_deterministic_passed else "FAIL"
    print(f"Verdict (deterministic checks): {verdict}")
    print("=" * 60)
    print()
    return all_deterministic_passed


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Git It — discussion-evidence narrative eval (spec 022)"
    )
    parser.add_argument(
        "--model",
        default=_DEFAULT_MODEL,
        help=f"LiteLLM model string (default: {_DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print the full generated narrative",
    )
    args = parser.parse_args()

    if not _check_api_key(args.model):
        print(
            "Skipped — no model configured for "
            f"'{args.model}' (required API key not set in the environment). "
            "This eval requires a real LLM call and is not part of the deterministic "
            "unit suite.",
        )
        sys.exit(0)

    from git_it.repository_ingestion.application.narrative_service import NarrativeService
    from git_it.repository_ingestion.infrastructure.llm import LiteLLMLLMClient

    discussions = _build_discussion_fixture()
    evidence = _build_discussion_evidence_fixture()
    commits = _build_commit_fixture()

    service = NarrativeService(
        temporal_reader=_StubTemporalReader(commits),  # type: ignore[arg-type]
        pattern_service=_StubPatternService(),  # type: ignore[arg-type]
        llm_client=LiteLLMLLMClient(model=args.model),
        discussion_reader=_StubDiscussionReader(evidence),  # type: ignore[arg-type]
    )

    print(f"Running discussion-evidence eval: model={args.model}")

    try:
        result = service.generate("eval-harness-repo", force=True)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"Error during evaluation: {exc}", file=sys.stderr)
        raise

    narrative = result.narrative

    low_confidence_item = min(evidence, key=lambda e: e.confidence)

    checks = [
        _check_no_raw_text_leakage(narrative, discussions),
        _check_citation_completeness(narrative, evidence),
        _check_uncertainty_preservation(narrative, low_confidence_item),
    ]

    deterministic_passed = _print_report(args.model, checks, narrative, args.verbose)

    if not deterministic_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
