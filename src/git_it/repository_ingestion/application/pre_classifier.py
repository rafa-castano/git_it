"""CommitPreClassifier — stateless noise/signal pre-filter for commit analysis."""

import re
from dataclasses import dataclass
from typing import Literal

from git_it.repository_ingestion.application.commit_query_service import CommitRecord
from git_it.repository_ingestion.domain.analysis import CommitCategory

# ---------------------------------------------------------------------------
# Output type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CommitPreClassification:
    decision: Literal["skip", "include", "sample"]
    reason: str  # non-empty human-readable explanation
    auto_category: CommitCategory | None = None  # set when decision == "skip"


# ---------------------------------------------------------------------------
# Compiled patterns — built once at module load
# ---------------------------------------------------------------------------

# Skip: Dependabot bump  →  "bump <pkg> from <ver> to <ver>"
_RE_DEPENDABOT = re.compile(r"^bump\s+\S+\s+from\s+\S+\s+to\s+\S+", re.IGNORECASE)

# Skip: conventional deps prefixes
_CONVENTIONAL_DEPS_PREFIXES = (
    "chore(deps):",
    "chore(deps-dev):",
    "build(deps):",
    "build(deps-dev):",
)

# Skip: lock file update — starts with "update " AND contains a lock-file name
_LOCK_FILE_NAMES = (
    "go.sum",
    "cargo.lock",
    "package-lock.json",
    "yarn.lock",
    "poetry.lock",
    "pnpm-lock.yaml",
    "pipfile.lock",
)

# Skip: format-only prefixes
_FORMAT_PREFIXES = (
    "apply black",
    "run prettier",
    "cargo fmt",
    "apply rustfmt",
    "style: format",
    "chore: format",
    "apply linting",
    "auto-format",
    "autoformat",
)

# Skip: format-only exact first lines
_FORMAT_EXACT = ("gofmt", "rustfmt")

# Skip: release prefixes
_RELEASE_PREFIXES = (
    "chore: release",
    "release v",
    "release: v",
    "bump version to",
    "chore: bump version",
)

# Skip: changelog prefixes
_CHANGELOG_PREFIXES = (
    "update changelog",
    "chore: update changelog",
    "add changelog entry",
)

# Skip: CI/automation prefixes
_CI_PREFIXES = (
    "ci: update",
    "ci: fix",
    "update github actions",
    "create codeowners",
    "add .github/",
)

# Include: breaking scope  →  feat(scope)!: ...  or  fix!: ...
_RE_BREAKING_SCOPE = re.compile(
    r"^(feat|fix|refactor|perf|chore)(\([^)]+\))?!:",
    re.IGNORECASE,
)

# Include: feat commit
_RE_FEAT = re.compile(r"^feat(\([^)]*\))?:", re.IGNORECASE)

# Include: fix commit (but NOT if first 20 chars contain "typo")
_RE_FIX = re.compile(r"^fix(\([^)]*\))?:", re.IGNORECASE)

# Include: refactor commit
_RE_REFACTOR = re.compile(r"^refactor(\([^)]*\))?:", re.IGNORECASE)

# Include: perf commit
_RE_PERF = re.compile(r"^perf(\([^)]*\))?:", re.IGNORECASE)

# Include: security / auth / migration / critical keywords in full message
_SECURITY_KEYWORDS = ("security", "vulnerability", "cve-", "exploit", "injection", "xss", "csrf")
_AUTH_KEYWORDS = ("authentication", "authorization", "credential", "oauth", "saml")
_MIGRATION_KEYWORDS = ("migration", "schema migration", "db migration")
_CRITICAL_KEYWORDS = ("hotfix", "critical fix", "urgent fix")


def _first_line(message: str) -> str:
    return message.splitlines()[0]


def _fl_lower(message: str) -> str:
    return _first_line(message).lower()


class CommitPreClassifier:
    """Stateless pre-classifier: decides skip / include / sample for a commit."""

    def classify(self, commit: CommitRecord) -> CommitPreClassification:
        skip_result = self._check_skip(commit)
        if skip_result is not None:
            return skip_result

        include_result = self._check_include(commit)
        if include_result is not None:
            return include_result

        return CommitPreClassification(decision="sample", reason="No special signal detected")

    # ------------------------------------------------------------------
    # Skip detection
    # ------------------------------------------------------------------

    def _check_skip(self, commit: CommitRecord) -> CommitPreClassification | None:
        fl = _fl_lower(commit.message)

        # Merge commit by structure (two or more parents)
        if len(commit.parent_shas) > 1:
            return self._skip("merge commit detected by multiple parents")

        # Dependabot bump
        if _RE_DEPENDABOT.match(fl):
            return self._skip("dependabot dependency bump")

        # Conventional deps
        for prefix in _CONVENTIONAL_DEPS_PREFIXES:
            if fl.startswith(prefix):
                return self._skip(f"conventional dependency update ({prefix})")

        # Snyk bot
        if fl.startswith("[snyk]"):
            return self._skip("snyk bot commit")

        # Renovate bot
        if (
            fl.startswith("renovate:")
            or fl.startswith("update(renovate):")
            or fl.startswith("fix(renovate):")
        ):
            return self._skip("renovate bot commit")

        # Merge PR message
        if fl.startswith("merge pull request #"):
            return self._skip("merge pull request commit")

        # Merge branch message
        if fl.startswith("merge branch '") or fl.startswith("merge remote-tracking branch"):
            return self._skip("merge branch commit")

        # Lock file update: starts with "update " AND contains a lock-file name
        if fl.startswith("update ") and any(lock in fl for lock in _LOCK_FILE_NAMES):
            return self._skip("lock file update commit")

        # Format-only (prefix)
        for prefix in _FORMAT_PREFIXES:
            if fl.startswith(prefix):
                return self._skip(f"formatting-only commit ({prefix})")

        # Format-only (exact)
        if fl.strip() in _FORMAT_EXACT:
            return self._skip(f"formatting-only commit ({fl.strip()})")

        # Release
        for prefix in _RELEASE_PREFIXES:
            if fl.startswith(prefix):
                return self._skip(f"release commit ({prefix})")

        # Changelog
        for prefix in _CHANGELOG_PREFIXES:
            if fl.startswith(prefix):
                return self._skip(f"changelog update ({prefix})")

        # CI/automation (prefix)
        for prefix in _CI_PREFIXES:
            if fl.startswith(prefix):
                return self._skip(f"CI/automation commit ({prefix})")

        # CI/automation: contains [skip ci]
        if "[skip ci]" in fl:
            return self._skip("commit contains [skip ci]")

        return None

    # ------------------------------------------------------------------
    # Include detection
    # ------------------------------------------------------------------

    def _check_include(self, commit: CommitRecord) -> CommitPreClassification | None:
        fl = _first_line(commit.message)
        full_lower = commit.message.lower()

        # Breaking scope: feat(scope)!: ...
        if _RE_BREAKING_SCOPE.match(fl):
            return self._include("breaking change scope detected in conventional commit")

        # BREAKING CHANGE anywhere in full message
        if "breaking change" in full_lower:
            return self._include("BREAKING CHANGE footer detected in commit body")

        # Feature commit
        if _RE_FEAT.match(fl) or fl.lower().startswith("feature:"):
            return self._include("feature commit")

        # Bug fix (but NOT if first 20 chars of first line contain "typo")
        if _RE_FIX.match(fl) or fl.lower().startswith("bugfix:"):
            if "typo" not in fl[:20].lower():
                return self._include("bug fix commit")

        # Refactor commit
        if _RE_REFACTOR.match(fl):
            return self._include("refactor commit")

        # Performance commit
        if _RE_PERF.match(fl):
            return self._include("performance commit")

        # Revert commit
        fl_lower = fl.lower()
        if fl_lower.startswith("revert:") or (
            fl_lower.startswith("revert ") and len(fl_lower) > len("revert ")
        ):
            return self._include("revert commit")

        # Security keywords
        for kw in _SECURITY_KEYWORDS:
            if kw in full_lower:
                return self._include(f"security-related commit (contains '{kw}')")

        # Auth keywords
        for kw in _AUTH_KEYWORDS:
            if kw in full_lower:
                return self._include(f"authentication/authorization commit (contains '{kw}')")

        # Migration keywords
        for kw in _MIGRATION_KEYWORDS:
            if kw in full_lower:
                return self._include(f"migration commit (contains '{kw}')")

        # Critical keywords
        for kw in _CRITICAL_KEYWORDS:
            if kw in full_lower:
                return self._include(f"critical commit (contains '{kw}')")

        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _skip(reason: str) -> CommitPreClassification:
        return CommitPreClassification(
            decision="skip",
            reason=reason,
            auto_category=CommitCategory.BUILD,
        )

    @staticmethod
    def _include(reason: str) -> CommitPreClassification:
        return CommitPreClassification(decision="include", reason=reason)
