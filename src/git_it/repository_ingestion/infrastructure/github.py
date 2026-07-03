"""GitHub API adapter for fetching PR and issue context per commit SHA.

Uses stdlib urllib.request only — no third-party dependencies.
The token is read from the caller; it is never logged.
"""

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Protocol

from git_it.repository_ingestion.domain.github_context import GithubContext
from git_it.repository_ingestion.domain.repo_metadata import LanguageBreakdown, RepoMetadata

_logger = logging.getLogger(__name__)

_ISSUE_REF_RE = re.compile(r"(?:closes?|fixes?|resolves?)\s+#(\d+)", re.IGNORECASE)
_MAX_PR_BODY_CHARS = 1000
_MAX_ISSUE_BODY_CHARS = 500
_MAX_ISSUES = 3
_TIMEOUT = 10


class GithubContextCache(Protocol):
    """Structural interface for GitHub context cache implementations."""

    def is_cached(self, repository_id: str, commit_sha: str) -> bool: ...

    def get_cached(self, repository_id: str, commit_sha: str) -> GithubContext | None: ...

    def save(self, repository_id: str, commit_sha: str, context: GithubContext | None) -> None: ...


class GithubContextFetcher:
    """Fetches GitHub PR and issue context for a commit SHA.

    Implements GithubContextReader (Protocol) — see ports.py.
    Cache is consulted before any network call.
    """

    def __init__(
        self,
        *,
        cache: GithubContextCache,
        token: str | None = None,
    ) -> None:
        self._cache = cache
        self._token = token

    def get_github_context(
        self,
        *,
        repository_id: str,
        canonical_url: str,
        commit_sha: str,
    ) -> GithubContext | None:
        if self._token is None:
            _logger.debug("github enrichment skipped: no token")
            return None

        parsed = _parse_owner_repo(canonical_url)
        if parsed is None:
            _logger.debug("github enrichment skipped: not a GitHub URL (%s)", canonical_url)
            return None
        owner, repo = parsed

        if self._cache.is_cached(repository_id, commit_sha):
            _logger.debug("github context cache hit for %s", commit_sha[:8])
            return self._cache.get_cached(repository_id, commit_sha)

        return self._fetch_and_cache(
            owner=owner,
            repo=repo,
            repository_id=repository_id,
            commit_sha=commit_sha,
        )

    def _fetch_and_cache(
        self,
        *,
        owner: str,
        repo: str,
        repository_id: str,
        commit_sha: str,
    ) -> GithubContext | None:
        pr_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{commit_sha}/pulls"
        try:
            prs = self._api_get(pr_url)
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 403):
                _logger.warning(
                    "github api rate-limited or forbidden (HTTP %d) for %s",
                    exc.code,
                    commit_sha[:8],
                )
                return None  # transient — do NOT cache
            if exc.code == 401:
                _logger.warning("github api unauthorized (HTTP 401) — check GITHUB_TOKEN")
                return None  # bad token — do NOT cache
            if exc.code == 404:
                # No PR found — write negative cache entry.
                self._cache.save(repository_id, commit_sha, None)
                return None
            _logger.warning("github api error HTTP %d for %s", exc.code, commit_sha[:8])
            return None
        except (TimeoutError, OSError) as exc:
            _logger.warning(
                "github api network error for %s: %s", commit_sha[:8], type(exc).__name__
            )
            return None

        if not prs:
            # Empty array — write negative cache entry.
            self._cache.save(repository_id, commit_sha, None)
            return None

        pr = prs[0]
        raw_number = pr.get("number")
        pr_number: int | None = int(str(raw_number)) if raw_number is not None else None
        raw_title = pr.get("title")
        pr_title: str | None = str(raw_title) if raw_title is not None else None
        raw_body = pr.get("body")
        pr_body: str | None = str(raw_body) if raw_body else None

        linked_issue_numbers = _parse_linked_issues(pr_body or "")[:_MAX_ISSUES]
        issue_bodies: list[str] = []
        issue_numbers_found: list[int] = []
        for issue_num in linked_issue_numbers:
            body = _fetch_issue_body(
                owner=owner,
                repo=repo,
                number=issue_num,
                token=self._token,  # type: ignore[arg-type]
            )
            if body is not None:
                issue_bodies.append(body)
                issue_numbers_found.append(issue_num)

        ctx = GithubContext(
            pr_number=pr_number,
            pr_title=pr_title,
            pr_body=pr_body,
            issue_numbers=tuple(issue_numbers_found),
            issue_bodies=tuple(issue_bodies),
            has_pr=True,
        )
        self._cache.save(repository_id, commit_sha, ctx)
        return ctx

    def _api_get(self, url: str) -> list[dict[str, object]]:
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("Authorization", f"Bearer {self._token}")
        req.add_header("User-Agent", "git-it/1.0")
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # type: ignore[arg-type]
            return json.loads(resp.read())  # type: ignore[no-any-return]


class GithubRepoMetadataFetcher:
    """Fetches repository-level GitHub metadata: star count and language breakdown.

    Independent of GithubContextFetcher (per-commit PR/issue enrichment) — this
    class is called at most once per ingestion, not once per commit, so it has no
    cache. Best-effort: returns None whenever the token is absent, the URL isn't
    GitHub, or the stars call fails — ingestion must never hard-fail because of
    this. A languages-call failure alone only empties the languages field; stars
    is the headline value this feature exists to show (see spec 019).
    """

    def __init__(self, *, token: str | None = None) -> None:
        self._token = token

    def fetch_repo_metadata(self, canonical_url: str) -> RepoMetadata | None:
        if self._token is None:
            _logger.debug("repo metadata fetch skipped: no token")
            return None

        parsed = _parse_owner_repo(canonical_url)
        if parsed is None:
            _logger.debug("repo metadata fetch skipped: not a GitHub URL (%s)", canonical_url)
            return None
        owner, repo = parsed

        stars = self._fetch_stars(owner, repo)
        if stars is None:
            return None
        languages = self._fetch_languages(owner, repo)
        return RepoMetadata(stars=stars, languages=languages)

    def _fetch_stars(self, owner: str, repo: str) -> int | None:
        url = f"https://api.github.com/repos/{owner}/{repo}"
        data = self._api_get_dict(url)
        if data is None:
            return None
        raw = data.get("stargazers_count")
        if not isinstance(raw, int) or isinstance(raw, bool):
            _logger.warning("github repo metadata: stargazers_count missing or invalid")
            return None
        return raw

    def _fetch_languages(self, owner: str, repo: str) -> tuple[LanguageBreakdown, ...]:
        url = f"https://api.github.com/repos/{owner}/{repo}/languages"
        data = self._api_get_dict(url)
        if data is None:
            return ()
        breakdown: list[LanguageBreakdown] = []
        for name, raw_bytes in data.items():
            if not isinstance(name, str):
                continue
            if isinstance(raw_bytes, bool) or not isinstance(raw_bytes, int):
                continue
            if raw_bytes < 0:
                continue
            breakdown.append(LanguageBreakdown(language=name, bytes=raw_bytes))
        return tuple(breakdown)

    def _api_get_dict(self, url: str) -> dict[str, object] | None:
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("Authorization", f"Bearer {self._token}")
        req.add_header("User-Agent", "git-it/1.0")
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # type: ignore[arg-type]
                raw = json.loads(resp.read())
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            _logger.warning("github repo metadata api error for %s: %s", url, type(exc).__name__)
            return None
        if not isinstance(raw, dict):
            _logger.warning("github repo metadata api returned non-object payload for %s", url)
            return None
        return raw


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_owner_repo(canonical_url: str) -> tuple[str, str] | None:
    """Extract (owner, repo) from https://github.com/owner/repo."""
    m = re.match(r"^https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", canonical_url)
    if m is None:
        return None
    return m.group(1), m.group(2)


def _parse_linked_issues(pr_body: str) -> list[int]:
    """Extract issue numbers referenced with closes/fixes/resolves keywords."""
    return [int(m) for m in _ISSUE_REF_RE.findall(pr_body)]


def _fetch_issue_body(owner: str, repo: str, number: int, token: str) -> str | None:
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("User-Agent", "git-it/1.0")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # type: ignore[arg-type]
            data = json.loads(resp.read())
        return data.get("body") or None
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        _logger.warning("failed to fetch issue #%d: %s", number, type(exc).__name__)
        return None
