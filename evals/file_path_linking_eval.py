"""
Git It — File-Path Linking Eval (spec 029, AC-09)

Measures whether case-study narratives reference files whose FULL repository-
relative path is present in the provided context (the "## Hotspot Files" block,
which injects full ``file_path`` values) as **full paths** (containing "/"),
rather than as bare basenames.

Spec 029 grounds file links in the repository's real file tree: the frontend
only links a backtick span when the path is an exact tree member, so a bare
basename like ``ports.py`` for a file that really lives at
``src/git_it/repository_ingestion/application/ports.py`` never becomes a link.
AC-09 closes that gap at the source by prompting the LLM to emit the full path.
This eval verifies the prompt actually changes the model's behavior.

Two deterministic-once-generated checks (they do not depend on the LLM's exact
phrasing, only on which path strings it emits):

1. Full-path usage — for every hotspot file whose basename appears anywhere in
   the narrative (a proxy for "this file was referenced"), the file's FULL path
   must also appear. A reference that only ever names the basename fails.
2. No bare-basename backticks — the banned "root basename" pattern: a
   backtick-wrapped bare basename (e.g. ``ports.py``) for a genuinely nested
   file must NOT appear anywhere in the narrative. That is exactly the span that
   spec 020 would have mislinked to the repo root (a 404).

This eval requires a real LLM call and is NOT part of the deterministic unit
suite. The offline, always-checkable guarantee (that both narrative system
prompts and the chat SYSTEM_PROMPT carry the full-path instruction) lives in the
unit tests: tests/unit/test_narrative_service.py and
tests/unit/test_chat_service.py.

Usage:
    uv run python evals/file_path_linking_eval.py [--model MODEL] [--verbose]
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
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
    from git_it.repository_ingestion.domain.patterns import PatternReport

_DEFAULT_MODEL = "anthropic/claude-haiku-4-5-20251001"

# Hotspot files with genuinely nested full paths — the LLM has each full path in
# its "## Hotspot Files" context, so per AC-09 it must reference them by that
# full path, never by the bare basename.
_HOTSPOT_PATHS = (
    "src/git_it/repository_ingestion/application/ports.py",
    "src/git_it/repository_ingestion/application/narrative_service.py",
    "src/git_it/chat/service.py",
)


def _check_api_key(model: str) -> bool:
    """Return True if the required API key for *model* is present.

    Mirrors evals/discussion_evidence_eval.py — returns a bool so this eval can
    print a clean "skipped" message and exit 0 where no LLM is configured.
    """
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
# Fixtures — commits + hotspots whose full paths are in the prompt context.
# ---------------------------------------------------------------------------


def _build_commit_fixture() -> list[TimestampedAnalysis]:
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
                summary=(
                    "Defined the ingestion application ports and grew the narrative "
                    "service that assembles the case study."
                ),
                category=CommitCategory.FEATURE,
                risk_level=RiskLevel.MEDIUM,
                confidence=0.85,
                affected_components=["ingestion", "narrative"],
            ),
            committed_at="2026-04-28T00:00:00Z",
        ),
        TimestampedAnalysis(
            analysis=CommitAnalysis(
                commit_sha="f6e5d4c3b2a1",
                summary="Hardened the chat service system prompt against injection.",
                category=CommitCategory.FEATURE,
                risk_level=RiskLevel.MEDIUM,
                confidence=0.8,
                affected_components=["chat"],
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
    """Returns a PatternReport whose hotspots carry the full nested file paths."""

    def detect(self, repository_id: str, *, hotspot_threshold: int = 3) -> PatternReport:
        from git_it.repository_ingestion.domain.patterns import Hotspot, PatternReport

        hotspots = [
            Hotspot(
                file_path=path,
                commit_count=12 - idx,
                total_insertions=120,
                total_deletions=40,
            )
            for idx, path in enumerate(_HOTSPOT_PATHS)
        ]
        return PatternReport(repository_id=repository_id, hotspots=hotspots)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    name: str
    passed: bool
    details: str


def _check_full_paths_used(narrative: str) -> CheckResult:
    """For every hotspot file that the narrative references (its basename shows
    up), the FULL repository-relative path must also appear (AC-09)."""
    violations: list[str] = []
    referenced_any = False
    for path in _HOTSPOT_PATHS:
        basename = path.rsplit("/", 1)[-1]
        if basename in narrative:
            referenced_any = True
            if path not in narrative:
                violations.append(f"{basename} referenced but full path {path!r} absent")
    passed = not violations
    if not referenced_any:
        details = (
            "Heuristic could not confirm any hotspot file was referenced by name "
            "in the narrative (no full-path violation to report)."
        )
    elif passed:
        details = "Every referenced hotspot file appears as its full repository-relative path."
    else:
        details = "Files referenced by basename without their full path: " + "; ".join(violations)
    return CheckResult(name="full_paths_used", passed=passed, details=details)


def _check_no_bare_basename_backticks(narrative: str) -> CheckResult:
    """The banned "root basename" pattern: a backtick-wrapped bare basename for a
    genuinely nested file must never appear — that is the span spec 020 would
    have mislinked to the repository root (AC-09 / §15)."""
    banned: list[str] = []
    for path in _HOTSPOT_PATHS:
        basename = path.rsplit("/", 1)[-1]
        if f"`{basename}`" in narrative:
            banned.append(f"`{basename}`")
    passed = not banned
    details = (
        "No backtick-wrapped bare basename found for any nested hotspot file."
        if passed
        else f"Banned bare-basename backtick span(s) found: {banned}"
    )
    return CheckResult(name="no_bare_basename_backticks", passed=passed, details=details)


# ---------------------------------------------------------------------------
# Report printing
# ---------------------------------------------------------------------------


def _print_report(model: str, results: list[CheckResult], narrative: str, verbose: bool) -> bool:
    """Print the report and return True iff all checks passed."""
    print()
    print("=" * 60)
    print("Git It — File-Path Linking Eval Report (spec 029)")
    print("=" * 60)
    print(f"Model: {model}")
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
        print("Generated narrative:")
        print("-" * 60)
        print(narrative)
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
    parser = argparse.ArgumentParser(
        description="Git It — file-path linking narrative eval (spec 029, AC-09)"
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

    commits = _build_commit_fixture()

    service = NarrativeService(
        temporal_reader=_StubTemporalReader(commits),  # type: ignore[arg-type]
        pattern_service=_StubPatternService(),  # type: ignore[arg-type]
        llm_client=LiteLLMLLMClient(model=args.model),
    )

    print(f"Running file-path linking eval: model={args.model}")

    try:
        result = service.generate("eval-harness-repo", force=True)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"Error during evaluation: {exc}", file=sys.stderr)
        raise

    narrative = result.narrative

    checks = [
        _check_full_paths_used(narrative),
        _check_no_bare_basename_backticks(narrative),
    ]

    passed = _print_report(args.model, checks, narrative, args.verbose)

    if not passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
