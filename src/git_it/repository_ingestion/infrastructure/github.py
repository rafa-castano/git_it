"""GitHub API adapter for fetching PR and issue context per commit SHA.

Uses stdlib urllib.request only — no third-party dependencies.
The token is read from the caller; it is never logged.
"""

import json
import logging
import re
import urllib.error
import urllib.request

from git_it.repository_ingestion.domain.github_context import GithubContext
from git_it.repository_ingestion.infrastructure.sqlite import SqliteGithubContextCache

_logger = logging.getLogger(__name__)

_ISSUE_REF_RE = re.compile(r"(?:closes?|fixes?|resolves?)\s+#(\d+)", re.IGNORECASE)
_MAX_PR_BODY_CHARS = 1000
_MAX_ISSUE_BODY_CHARS = 500
_MAX_ISSUES = 3
_TIMEOUT = 10


class GithubContextFetcher:
    """Fetches GitHub PR and issue context for a commit SHA.

    Implements GithubContextReader (Protocol) — see ports.py.
    Cache is consulted before any network call.
    """

    def __init__(
        self,
        *,
        cache: SqliteGithubContextCache,
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
