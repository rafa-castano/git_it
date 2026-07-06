"""
Git It — Release/Advisory Evidence Eval

Measures whether case-study narratives generated with GitHub Release and
Security Advisory evidence (spec 026) satisfy the properties the spec's
"Evaluation required" section demands:

1. Citation completeness — a release- or advisory-sourced claim in the
   narrative is accompanied by its `release_url`/`advisory_url`. Same
   heuristic as `discussion_evidence_eval.py`'s citation check.
2. No raw-text leakage — none of the untrusted, raw `Release.body` /
   `SecurityAdvisory.description` fixture text appears anywhere in the
   generated narrative. This is the deterministic, security-relevant check:
   only validated `ReleaseEvidence.summary`/`AdvisoryEvidence.summary` may
   ever reach the narrative, never the raw text fed to the summarizer.
3. Severity-vs-confidence guard — severity and confidence are independent
   axes. A critical-severity advisory's evidence must still be surfaced with
   its severity intact (deterministic: the word "critical" must appear
   somewhere in the narrative once that evidence appears used), even though
   the fixture deliberately pairs it with a *low-confidence* summary. A
   second, qualitative-only observation reports whether hedged language
   appears near that critical-severity mention — reported, not hard-failed,
   since some hedging about exploit specifics is legitimate and does not by
   itself mean severity was conflated with confidence.

Usage:
    uv run python evals/release_advisory_eval.py [--model MODEL]
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
    from git_it.repository_ingestion.domain.advisories import AdvisoryEvidence, SecurityAdvisory
    from git_it.repository_ingestion.domain.patterns import PatternReport
    from git_it.repository_ingestion.domain.releases import Release, ReleaseEvidence

_DEFAULT_MODEL = "anthropic/claude-haiku-4-5-20251001"

# Sentinel phrases embedded in the raw (untrusted) fixture Release.body /
# SecurityAdvisory.description text. These strings must NEVER appear in the
# generated narrative — only the corresponding validated
# ReleaseEvidence.summary / AdvisoryEvidence.summary strings (which paraphrase
# them) may.
_SENTINEL_BREAKING = "ZEBRA-QUUX-SENTINEL removed the legacy v1 authentication endpoint"
_SENTINEL_BUGFIX = "PLATYPUS-FOXTROT-SENTINEL fixed a race condition in the job scheduler"
_SENTINEL_SQLI = "WOMBAT-YANKEE-SENTINEL raw string concatenation enabled SQL injection"
_SENTINEL_LOWSEV = "IGUANA-TANGO-SENTINEL unbounded log growth could fill the disk"


def _check_api_key(model: str) -> bool:
    """Return True if the required API key for *model* is present.

    Mirrors `discussion_evidence_eval.py`'s `_check_api_key`, but returns a
    bool instead of exiting, so this eval can print a clean "skipped" message
    and exit 0 in an environment with no LLM configured (this eval must never
    hard-fail CI without a key).
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
# Fixtures: raw Release/SecurityAdvisory (untrusted, ephemeral) + matching
# ReleaseEvidence/AdvisoryEvidence (validated, persisted). The raw body/
# description text is what must NEVER leak into the narrative; only the
# *Evidence summary/*_url may.
# ---------------------------------------------------------------------------

_OWNER_REPO = "octo-org/octo-repo"


def _build_release_fixture() -> list[Release]:
    from git_it.repository_ingestion.domain.releases import Release

    return [
        Release(
            tag_name="v2.0.0",
            name="v2.0.0",
            body=(
                f"Breaking change release. {_SENTINEL_BREAKING} in favor of the new "
                "OAuth2 authentication flow."
            ),
            html_url=f"https://github.com/{_OWNER_REPO}/releases/tag/v2.0.0",
            published_at="2026-06-01T00:00:00Z",
            prerelease=False,
        ),
        Release(
            tag_name="v1.9.1",
            name="v1.9.1",
            body=(
                f"Bugfix release. {_SENTINEL_BUGFIX} that caused duplicate job "
                "execution under sustained load."
            ),
            html_url=f"https://github.com/{_OWNER_REPO}/releases/tag/v1.9.1",
            published_at="2026-05-15T00:00:00Z",
            prerelease=False,
        ),
    ]


def _build_release_evidence_fixture() -> list[ReleaseEvidence]:
    from git_it.repository_ingestion.domain.releases import ReleaseEvidence

    now = datetime.now(UTC)
    return [
        ReleaseEvidence(
            tag_name="v2.0.0",
            release_url=f"https://github.com/{_OWNER_REPO}/releases/tag/v2.0.0",
            claim_type="breaking_change",
            summary=(
                "Release v2.0.0 removes the legacy v1 authentication endpoint in "
                "favor of OAuth2, a breaking change for existing API clients."
            ),
            confidence=0.9,
            limitations=[],
            source_inputs=["v2.0.0"],
            generated_at=now,
            model="eval-fixture",
        ),
        ReleaseEvidence(
            tag_name="v1.9.1",
            release_url=f"https://github.com/{_OWNER_REPO}/releases/tag/v1.9.1",
            claim_type="bugfix_release",
            summary=(
                "Release v1.9.1 fixes a race condition in the job scheduler that "
                "caused duplicate job execution under sustained load."
            ),
            confidence=0.85,
            limitations=[],
            source_inputs=["v1.9.1"],
            generated_at=now,
            model="eval-fixture",
        ),
    ]


def _build_advisory_fixture() -> list[SecurityAdvisory]:
    from git_it.repository_ingestion.domain.advisories import SecurityAdvisory

    return [
        SecurityAdvisory(
            ghsa_id="GHSA-pmv8-rq9r-6j72",
            cve_id="CVE-2026-30001",
            summary="SQL injection in the search endpoint",
            description=(
                f"{_SENTINEL_SQLI} in the search endpoint, allowing an "
                "unauthenticated attacker to exfiltrate arbitrary database rows."
            ),
            severity="critical",
            html_url=f"https://github.com/{_OWNER_REPO}/security/advisories/GHSA-pmv8-rq9r-6j72",
            published_at="2026-05-20T00:00:00Z",
        ),
        SecurityAdvisory(
            ghsa_id="GHSA-abcd-1234-wxyz",
            cve_id=None,
            summary="Minor denial-of-service via unbounded log growth",
            description=(
                f"{_SENTINEL_LOWSEV}, potentially exhausting disk space over an "
                "extended period of continuous operation."
            ),
            severity="low",
            html_url=f"https://github.com/{_OWNER_REPO}/security/advisories/GHSA-abcd-1234-wxyz",
            published_at="2026-05-25T00:00:00Z",
        ),
    ]


def _build_advisory_evidence_fixture() -> list[AdvisoryEvidence]:
    from git_it.repository_ingestion.domain.advisories import AdvisoryEvidence

    now = datetime.now(UTC)
    return [
        # Deliberately pairs a CRITICAL severity with a LOW confidence summary —
        # severity and confidence are independent axes (spec 026's Evaluation
        # required section). The narrative must still surface "critical"
        # intact; it must not be silently downgraded because the summarizer's
        # own confidence in its paraphrase happens to be low.
        AdvisoryEvidence(
            ghsa_id="GHSA-pmv8-rq9r-6j72",
            advisory_url=(
                f"https://github.com/{_OWNER_REPO}/security/advisories/GHSA-pmv8-rq9r-6j72"
            ),
            severity="critical",
            summary=(
                "A critical SQL injection vulnerability in the search endpoint "
                "allowed an unauthenticated attacker to exfiltrate arbitrary "
                "database rows; it was fixed by switching to parameterized queries."
            ),
            confidence=0.35,
            limitations=[
                "Summary derived from a single advisory description; independent "
                "exploit verification was not performed."
            ],
            source_inputs=["GHSA-pmv8-rq9r-6j72"],
            generated_at=now,
            model="eval-fixture",
        ),
        AdvisoryEvidence(
            ghsa_id="GHSA-abcd-1234-wxyz",
            advisory_url=(
                f"https://github.com/{_OWNER_REPO}/security/advisories/GHSA-abcd-1234-wxyz"
            ),
            severity="low",
            summary=(
                "A low-severity denial-of-service issue from unbounded log growth "
                "could eventually exhaust disk space."
            ),
            confidence=0.9,
            limitations=[],
            source_inputs=["GHSA-abcd-1234-wxyz"],
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
                summary="Migrated the authentication flow to OAuth2.",
                category=CommitCategory.FEATURE,
                risk_level=RiskLevel.MEDIUM,
                confidence=0.85,
                affected_components=["auth"],
            ),
            committed_at="2026-05-28T00:00:00Z",
        ),
        TimestampedAnalysis(
            analysis=CommitAnalysis(
                commit_sha="f6e5d4c3b2a1",
                summary="Fixed a race condition in the background job scheduler.",
                category=CommitCategory.BUGFIX,
                risk_level=RiskLevel.MEDIUM,
                confidence=0.8,
                affected_components=["scheduler"],
            ),
            committed_at="2026-05-12T00:00:00Z",
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


class _StubReleaseEvidenceReader:
    def __init__(self, evidence: list[ReleaseEvidence]) -> None:
        self._evidence = evidence

    def get_release_evidence(self, repository_id: str) -> list[ReleaseEvidence]:
        return self._evidence


class _StubAdvisoryEvidenceReader:
    def __init__(self, evidence: list[AdvisoryEvidence]) -> None:
        self._evidence = evidence

    def get_advisory_evidence(self, repository_id: str) -> list[AdvisoryEvidence]:
        return self._evidence


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    name: str
    passed: bool
    details: str


def _check_no_raw_text_leakage(
    narrative: str,
    releases: list[Release],
    advisories: list[SecurityAdvisory],
) -> CheckResult:
    """Deterministic, security-relevant check: no raw fixture text may appear.

    Mirrors `discussion_evidence_eval.py`'s equivalent check: each fixture
    Release/SecurityAdvisory embeds a unique sentinel phrase directly inside
    its raw `body`/`description`. Asserting that none of those sentinel
    substrings — nor the raw fields themselves, as a defense-in-depth check —
    appear anywhere in the generated narrative is the practical, deterministic
    form of "no substring of the raw release/advisory text leaked into LLM
    output."
    """
    sentinels = (_SENTINEL_BREAKING, _SENTINEL_BUGFIX, _SENTINEL_SQLI, _SENTINEL_LOWSEV)
    leaked: list[str] = [s for s in sentinels if s in narrative]

    # Defense-in-depth: also flag verbatim reproduction of an entire raw field.
    for r in releases:
        if r.body and r.body in narrative:
            leaked.append(f"{r.tag_name}.body")
    for a in advisories:
        if a.description in narrative:
            leaked.append(f"{a.ghsa_id}.description")

    passed = not leaked
    details = (
        "No sentinel phrase or raw release body/advisory description substring "
        "found in the narrative."
        if passed
        else f"Raw release/advisory text leaked into the narrative: {leaked}"
    )
    return CheckResult(name="no_raw_text_leakage", passed=passed, details=details)


def _evidence_appears_used(summary: str, narrative: str) -> bool:
    """Same heuristic as `discussion_evidence_eval.py`'s citation-completeness
    check: at least 2 distinctive (len > 5) words from the summary showing up
    in the (lowercased) narrative is treated as "this evidence was used"."""
    significant_words = [w.strip(".,;:()").lower() for w in summary.split() if len(w) > 5]
    hits = sum(1 for w in significant_words if w in narrative)
    return bool(significant_words) and hits >= min(2, len(significant_words))


def _check_citation_completeness(
    narrative: str,
    release_evidence: list[ReleaseEvidence],
    advisory_evidence: list[AdvisoryEvidence],
) -> CheckResult:
    """Practical, non-brittle heuristic for citation completeness — same
    approach as `discussion_evidence_eval.py`'s check, applied to both
    ReleaseEvidence.release_url and AdvisoryEvidence.advisory_url."""
    missing_citations: list[str] = []
    used_any_evidence = False
    lowered_narrative = narrative.lower()

    for item in release_evidence:
        if _evidence_appears_used(item.summary, lowered_narrative):
            used_any_evidence = True
            if item.release_url not in narrative:
                missing_citations.append(item.release_url)

    for adv in advisory_evidence:
        if _evidence_appears_used(adv.summary, lowered_narrative):
            used_any_evidence = True
            if adv.advisory_url not in narrative:
                missing_citations.append(adv.advisory_url)

    passed = not missing_citations
    if not used_any_evidence:
        details = (
            "Heuristic could not confirm any release/advisory evidence was clearly "
            "used in the narrative (no citation-completeness violation to report)."
        )
    elif passed:
        details = "Every release/advisory evidence item that appears used is cited by its URL."
    else:
        details = (
            f"Release/advisory evidence used without its citation URL present: {missing_citations}"
        )
    return CheckResult(name="citation_completeness", passed=passed, details=details)


def _check_severity_intact(narrative: str, critical_advisory: AdvisoryEvidence) -> CheckResult:
    """Deterministic severity-vs-confidence guard (spec 026's Evaluation
    required section): severity and confidence are independent axes. The
    fixture's critical-severity advisory deliberately carries a LOW-confidence
    summary (0.35) — this check asserts that once that evidence appears used
    in the narrative, its "critical" severity is still surfaced, i.e. the low
    confidence in the *summary* was not allowed to silently downgrade or drop
    the *severity* label.
    """
    lowered_narrative = narrative.lower()
    used = _evidence_appears_used(critical_advisory.summary, lowered_narrative)

    if not used:
        return CheckResult(
            name="severity_intact",
            passed=True,
            details=(
                "Heuristic could not confirm the critical-severity advisory evidence "
                "was clearly used in the narrative (no severity-conflation violation "
                "to report)."
            ),
        )

    severity_present = "critical" in lowered_narrative
    passed = severity_present
    details = (
        "The critical-severity advisory's evidence appears used in the narrative "
        "and its 'critical' severity label is present — severity was not "
        "downgraded despite the summary's low (0.35) confidence."
        if passed
        else (
            "The critical-severity advisory's evidence appears used in the "
            "narrative, but the word 'critical' is absent — its severity may have "
            "been conflated with the summary's low confidence."
        )
    )
    return CheckResult(name="severity_intact", passed=passed, details=details)


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


def _check_severity_confidence_independence_qualitative(
    narrative: str, critical_advisory: AdvisoryEvidence
) -> CheckResult:
    """Best-effort, qualitative check (per spec 026's Evaluation required
    section: "if it's hard to make fully deterministic, report it
    qualitatively"). Reports whether hedged language appears in the narrative
    alongside the critical-severity advisory's citation — this is informational
    only and never fails the eval, since some hedging about exploit specifics
    is legitimate and does not by itself prove severity was conflated with
    confidence.
    """
    lowered = narrative.lower()
    hedges_found = [p for p in _HEDGE_PHRASES if p in lowered]
    passed = True  # qualitative signal only — never fails the eval
    details = (
        f"Hedged language also present in the narrative: {hedges_found}. This is "
        "a qualitative observation (the low-confidence summary may legitimately "
        "be hedged) — not evidence of severity conflation by itself, since "
        "'severity_intact' above already confirms the critical label survived."
        if hedges_found
        else f"No hedged language found near {critical_advisory.advisory_url}; "
        "qualitative observation only."
    )
    return CheckResult(
        name="severity_confidence_independence_qualitative", passed=passed, details=details
    )


# ---------------------------------------------------------------------------
# Report printing
# ---------------------------------------------------------------------------


def _print_report(model: str, results: list[CheckResult], narrative: str, verbose: bool) -> bool:
    """Print the report and return True iff the deterministic checks passed."""
    print()
    print("=" * 60)
    print("Git It — Release/Advisory Evidence Eval Report")
    print("=" * 60)
    print(f"Model: {model}")
    print()

    deterministic_names = {"no_raw_text_leakage", "citation_completeness", "severity_intact"}
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
        description="Git It — release/advisory-evidence narrative eval (spec 026)"
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

    releases = _build_release_fixture()
    release_evidence = _build_release_evidence_fixture()
    advisories = _build_advisory_fixture()
    advisory_evidence = _build_advisory_evidence_fixture()
    commits = _build_commit_fixture()

    service = NarrativeService(
        temporal_reader=_StubTemporalReader(commits),  # type: ignore[arg-type]
        pattern_service=_StubPatternService(),  # type: ignore[arg-type]
        llm_client=LiteLLMLLMClient(model=args.model),
        release_evidence_reader=_StubReleaseEvidenceReader(release_evidence),  # type: ignore[arg-type]
        advisory_evidence_reader=_StubAdvisoryEvidenceReader(advisory_evidence),  # type: ignore[arg-type]
    )

    print(f"Running release/advisory-evidence eval: model={args.model}")

    try:
        result = service.generate("eval-harness-repo", force=True)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"Error during evaluation: {exc}", file=sys.stderr)
        raise

    narrative = result.narrative

    critical_advisory = next(a for a in advisory_evidence if a.severity == "critical")

    checks = [
        _check_no_raw_text_leakage(narrative, releases, advisories),
        _check_citation_completeness(narrative, release_evidence, advisory_evidence),
        _check_severity_intact(narrative, critical_advisory),
        _check_severity_confidence_independence_qualitative(narrative, critical_advisory),
    ]

    deterministic_passed = _print_report(args.model, checks, narrative, args.verbose)

    if not deterministic_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
