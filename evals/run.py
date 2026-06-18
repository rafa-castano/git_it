"""
Git It — Evaluation Harness

Measures LLM commit classification accuracy against a golden fixture.

Usage:
    uv run python evals/run.py [--model MODEL] [--fixture PATH] [--output PATH] [--verbose]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: ensure the project src is importable when run from the repo root.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_DEFAULT_MODEL = "anthropic/claude-haiku-4-5-20251001"
_DEFAULT_FIXTURE = Path(__file__).parent / "golden_commits.json"


# ---------------------------------------------------------------------------
# Minimal stub: CommitReader that returns nothing (analyze_commit does not use it)
# ---------------------------------------------------------------------------

from git_it.repository_ingestion.application.commit_query_service import CommitRecord  # noqa: E402


class _NoopCommitReader:
    """Stub CommitReader — analyze_commit() never calls list_commits_for_repository."""

    def list_commits_for_repository(
        self,
        repository_id: str,
        *,
        limit: int | None = None,
        order: str = "newest",
        since: str | None = None,
        until: str | None = None,
    ) -> list[CommitRecord]:
        return []


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class EvalResult:
    sha: str
    message: str
    expected_category: str
    expected_risk_level: str
    predicted_category: str
    predicted_risk_level: str
    category_correct: bool
    risk_correct: bool
    full_analysis: object | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_fixture(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"Fixture must be a JSON array, got {type(data)}")
    return data


def _make_commit_record(entry: dict) -> CommitRecord:
    """Build a CommitRecord from a golden fixture entry."""
    return CommitRecord(
        repository_id="eval-harness",
        sha=entry["sha"],
        committed_at=entry["committed_at"],
        message=entry["message"],
        author_name=entry["author_name"],
        committer_name=entry.get("author_name", "unknown"),
        parent_shas=(),  # single-parent — avoids pre-classifier merge-skip
    )


def _check_api_key(model: str) -> None:
    """Exit with a clear error if the required API key is missing."""
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
            if not os.environ.get(env_var):
                print(
                    f"Error: model '{model}' requires the {env_var} environment variable.\n"
                    f"Set it with:  export {env_var}=<your-key>",
                    file=sys.stderr,
                )
                sys.exit(1)
            return

    # Fallback: if the model string contains "/" (provider/model format) and we
    # did not match a known provider, warn but do not exit — the user may be
    # using a custom LiteLLM router.
    if "/" in model:
        provider_prefix = model.split("/")[0]
        print(
            f"Warning: unknown provider '{provider_prefix}'. "
            "Make sure the required API key is set before running.",
            file=sys.stderr,
        )


def _percent(correct: int, total: int) -> str:
    if total == 0:
        return "n/a"
    return f"{correct / total * 100:.1f}%"


# ---------------------------------------------------------------------------
# Core evaluation loop
# ---------------------------------------------------------------------------


def run_eval(
    model: str,
    fixture_path: Path,
    *,
    verbose: bool = False,
) -> tuple[list[EvalResult], dict]:
    """Run the evaluation and return (results, summary_dict)."""
    from git_it.repository_ingestion.application.commit_analysis_service import (
        CommitAnalysisService,
    )
    from git_it.repository_ingestion.infrastructure.llm import InstructorCommitAnalysisAdapter

    golden = _load_fixture(fixture_path)
    client = InstructorCommitAnalysisAdapter(model=model)
    service = CommitAnalysisService(
        reader=_NoopCommitReader(),  # type: ignore[arg-type]
        client=client,
        repo_context_reader=None,
        github_context_reader=None,
    )

    results: list[EvalResult] = []

    for idx, entry in enumerate(golden, start=1):
        sha = entry["sha"]
        message = entry["message"]
        expected_cat = entry["expected_category"]
        expected_risk = entry["expected_risk_level"]

        if verbose:
            print(f"\n[{idx}/{len(golden)}] sha={sha[:8]}  {message[:80]}")

        commit = _make_commit_record(entry)
        analysis = service.analyze_commit(commit, repo_context=None)

        predicted_cat = analysis.category.value
        predicted_risk = analysis.risk_level.value

        category_correct = predicted_cat == expected_cat
        risk_correct = predicted_risk == expected_risk

        result = EvalResult(
            sha=sha,
            message=message,
            expected_category=expected_cat,
            expected_risk_level=expected_risk,
            predicted_category=predicted_cat,
            predicted_risk_level=predicted_risk,
            category_correct=category_correct,
            risk_correct=risk_correct,
            full_analysis=analysis if verbose else None,
        )
        results.append(result)

        if verbose:
            cat_mark = "✓" if category_correct else "✗"
            risk_mark = "✓" if risk_correct else "✗"
            print(f"  category: {cat_mark} expected={expected_cat}  got={predicted_cat}")
            print(f"  risk    : {risk_mark} expected={expected_risk}  got={predicted_risk}")
            print(f"  summary : {analysis.summary[:120]}")

    return results, _build_summary(results, model, fixture_path)


def _build_summary(results: list[EvalResult], model: str, fixture_path: Path) -> dict:
    total = len(results)
    cat_correct = sum(1 for r in results if r.category_correct)
    risk_correct = sum(1 for r in results if r.risk_correct)
    combined_score = (cat_correct + risk_correct) / (total * 2) * 100 if total else 0.0

    # Per-category breakdown
    categories: dict[str, dict[str, int]] = {}
    for r in results:
        cat = r.expected_category
        if cat not in categories:
            categories[cat] = {"correct": 0, "total": 0}
        categories[cat]["total"] += 1
        if r.category_correct:
            categories[cat]["correct"] += 1

    failures = [
        {
            "sha": r.sha[:8],
            "message": r.message[:60],
            "expected_category": r.expected_category,
            "got_category": r.predicted_category,
            "expected_risk": r.expected_risk_level,
            "got_risk": r.predicted_risk_level,
            "category_ok": r.category_correct,
            "risk_ok": r.risk_correct,
        }
        for r in results
        if not r.category_correct or not r.risk_correct
    ]

    return {
        "model": model,
        "fixture": str(fixture_path),
        "total_commits": total,
        "category_correct": cat_correct,
        "risk_correct": risk_correct,
        "combined_score_pct": round(combined_score, 1),
        "per_category": categories,
        "failures": failures,
    }


# ---------------------------------------------------------------------------
# Report printing
# ---------------------------------------------------------------------------


def print_report(summary: dict, results: list[EvalResult]) -> None:
    total = summary["total_commits"]
    cat_correct = summary["category_correct"]
    risk_correct = summary["risk_correct"]
    combined = summary["combined_score_pct"]

    print()
    print("=" * 60)
    print("Git It — Eval Report")
    print("=" * 60)
    print(f"Model  : {summary['model']}")
    print(f"Fixture: {summary['fixture']}")
    print(f"Commits: {total}")
    print()
    print(f"Category accuracy  : {cat_correct}/{total}  ({_percent(cat_correct, total)})")
    print(f"Risk level accuracy: {risk_correct}/{total}  ({_percent(risk_correct, total)})")
    print(f"Combined score     : {combined}%")
    print()

    # Per-category breakdown
    print("Per-category breakdown:")
    for cat, counts in sorted(summary["per_category"].items()):
        c = counts["correct"]
        t = counts["total"]
        bar = "✓" * c + "✗" * (t - c)
        print(f"  {cat:<12} {c}/{t}  {_percent(c, t)}  {bar}")

    # Failures
    failures = summary["failures"]
    if failures:
        print()
        print("Failures:")
        for f in failures:
            cat_mark = "✓" if f["category_ok"] else "✗"
            risk_mark = "✓" if f["risk_ok"] else "✗"
            print(
                f"  sha {f['sha']}  "
                f"expected={f['expected_category']}  got={f['got_category']}  "
                f"cat:{cat_mark}  "
                f"risk: expected={f['expected_risk']}  got={f['got_risk']}  {risk_mark}"
            )
    else:
        print()
        print("No failures — all commits correctly classified.")

    print()

    # Pass/fail verdict
    passing_threshold = 75.0
    verdict = "PASS" if combined >= passing_threshold else "FAIL"
    print(f"Verdict: {verdict}  (threshold: {passing_threshold}%)")
    print("=" * 60)
    print()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Git It — evaluation harness for LLM commit classification accuracy"
    )
    parser.add_argument(
        "--model",
        default=_DEFAULT_MODEL,
        help=f"LiteLLM model string (default: {_DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=_DEFAULT_FIXTURE,
        help="Path to golden_commits.json fixture (default: evals/golden_commits.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write JSON report to this path in addition to stdout",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print each commit message and full predicted analysis",
    )
    args = parser.parse_args()

    # Validate API key before any LLM calls
    _check_api_key(args.model)

    fixture_path: Path = args.fixture
    if not fixture_path.exists():
        print(f"Error: fixture not found: {fixture_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Running eval: model={args.model}  fixture={fixture_path}")

    try:
        results, summary = run_eval(args.model, fixture_path, verbose=args.verbose)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"Error during evaluation: {exc}", file=sys.stderr)
        raise

    print_report(summary, results)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)
        print(f"JSON report written to: {args.output}")


if __name__ == "__main__":
    main()
