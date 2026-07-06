"""GitHub API adapter for fetching PR and issue context per commit SHA.

Uses stdlib urllib.request only — no third-party dependencies.
The token is read from the caller; it is never logged.
"""

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Protocol

from git_it.repository_ingestion.domain.advisories import SecurityAdvisory
from git_it.repository_ingestion.domain.discussions import Discussion
from git_it.repository_ingestion.domain.github_context import GithubContext
from git_it.repository_ingestion.domain.releases import Release
from git_it.repository_ingestion.domain.repo_metadata import LanguageBreakdown, RepoMetadata

_logger = logging.getLogger(__name__)

_ISSUE_REF_RE = re.compile(r"(?:closes?|fixes?|resolves?)\s+#(\d+)", re.IGNORECASE)
_MAX_PR_BODY_CHARS = 1000
_MAX_ISSUE_BODY_CHARS = 500
_MAX_ISSUES = 3
_TIMEOUT = 10

# Spec 022 (GitHub Discussions ingestion) config constants — env-var-backed,
# following the batch-74 "named constant by canonical layer" convention.
DISCUSSION_MIN_ENGAGEMENT_SCORE = int(os.environ.get("DISCUSSION_MIN_ENGAGEMENT_SCORE", "5"))
DISCUSSION_MIN_REPLY_COUNT = int(os.environ.get("DISCUSSION_MIN_REPLY_COUNT", "3"))
DISCUSSION_MAX_SUMMARIZED = int(os.environ.get("DISCUSSION_MAX_SUMMARIZED", "20"))
DISCUSSION_PAGE_SIZE = int(os.environ.get("DISCUSSION_PAGE_SIZE", "50"))
DISCUSSION_MAX_PAGES = int(os.environ.get("DISCUSSION_MAX_PAGES", "10"))

# Spec 026 (Releases + Security Advisories ingestion) config constants —
# env-var-backed, following the same batch-74 convention.
RELEASE_MAX_SUMMARIZED = int(os.environ.get("RELEASE_MAX_SUMMARIZED", "10"))
ADVISORY_MAX_SUMMARIZED = int(os.environ.get("ADVISORY_MAX_SUMMARIZED", "10"))

_GRAPHQL_URL = "https://api.github.com/graphql"

_DISCUSSIONS_QUERY = """
query($owner: String!, $repo: String!, $first: Int!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    discussions(first: $first, after: $cursor, orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes {
        number
        url
        title
        body
        category { name }
        answerChosenAt
        answer { body }
        upvoteCount
        reactions { totalCount }
        comments { totalCount }
        updatedAt
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
"""


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


class GithubDiscussionsFetcher:
    """Fetches a bounded, ranked subset of a repository's GitHub Discussions.

    Performs an inline GraphQL POST to https://api.github.com/graphql using the
    same urllib.request transport, Bearer token header, and timeout conventions
    as the REST-based fetchers in this module. Best-effort: returns [] on
    missing token, non-GitHub URL, GraphQL/HTTP/network error, timeout, rate
    limit, or malformed payload — never raises (spec 022).
    """

    def __init__(self, token: str | None) -> None:
        self._token = token

    def fetch_qualifying_discussions(self, canonical_url: str) -> list[Discussion]:
        if self._token is None:
            _logger.debug("discussions fetch skipped: no token")
            return []

        parsed = _parse_owner_repo(canonical_url)
        if parsed is None:
            _logger.debug("discussions fetch skipped: not a GitHub URL (%s)", canonical_url)
            return []
        owner, repo = parsed

        candidates = self._fetch_all_pages(owner, repo)
        qualifying = [d for d in candidates if _qualifies(d)]
        qualifying.sort(key=_ranking_key, reverse=True)
        return qualifying[:DISCUSSION_MAX_SUMMARIZED]

    def _fetch_all_pages(self, owner: str, repo: str) -> list[Discussion]:
        discussions: list[Discussion] = []
        cursor: str | None = None
        for _ in range(DISCUSSION_MAX_PAGES):
            page = self._fetch_page(owner, repo, cursor)
            if page is None:
                break
            nodes, has_next_page, end_cursor = page
            discussions.extend(nodes)
            if not has_next_page:
                break
            cursor = end_cursor
        return discussions

    def _fetch_page(
        self, owner: str, repo: str, cursor: str | None
    ) -> tuple[list[Discussion], bool, str | None] | None:
        variables = {
            "owner": owner,
            "repo": repo,
            "first": DISCUSSION_PAGE_SIZE,
            "cursor": cursor,
        }
        payload = json.dumps({"query": _DISCUSSIONS_QUERY, "variables": variables}).encode()
        req = urllib.request.Request(_GRAPHQL_URL, data=payload, method="POST")
        req.add_header("Authorization", f"Bearer {self._token}")
        req.add_header("Content-Type", "application/json")
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
            _logger.warning("discussions graphql api error: %s", type(exc).__name__)
            return None

        try:
            return _parse_page(raw)
        except (KeyError, TypeError, ValueError) as exc:
            _logger.warning("discussions graphql payload malformed: %s", type(exc).__name__)
            return None


class GithubReleasesFetcher:
    """Fetches a bounded set of published, non-draft GitHub releases.

    Uses the same urllib.request transport, Bearer token header, and 10s
    timeout as the other REST-based fetchers in this module. Best-effort:
    returns [] on missing token, non-GitHub URL, HTTP/network error, timeout,
    rate limit, or malformed payload — never raises (spec 026). Draft releases
    are filtered out before construction; prereleases are included.
    """

    def __init__(self, *, token: str | None = None) -> None:
        self._token = token

    def fetch_releases(self, canonical_url: str) -> list[Release]:
        if self._token is None:
            _logger.debug("releases fetch skipped: no token")
            return []

        parsed = _parse_owner_repo(canonical_url)
        if parsed is None:
            _logger.debug("releases fetch skipped: not a GitHub URL (%s)", canonical_url)
            return []
        owner, repo = parsed

        url = f"https://api.github.com/repos/{owner}/{repo}/releases"
        items = _api_get_list(url, self._token)
        if items is None:
            return []

        releases: list[Release] = []
        for item in items:
            if item.get("draft") is True:
                continue
            release = _parse_release(item)
            if release is not None:
                releases.append(release)
        return releases[:RELEASE_MAX_SUMMARIZED]


class GithubSecurityAdvisoriesFetcher:
    """Fetches a bounded set of published, non-withdrawn security advisories.

    Uses the same urllib.request transport, Bearer token header, and 10s
    timeout as the other REST-based fetchers in this module. Best-effort:
    returns [] on missing token, non-GitHub URL, HTTP/network error, timeout,
    rate limit, or malformed payload — never raises (spec 026). Withdrawn
    advisories are filtered out before construction.
    """

    def __init__(self, *, token: str | None = None) -> None:
        self._token = token

    def fetch_advisories(self, canonical_url: str) -> list[SecurityAdvisory]:
        if self._token is None:
            _logger.debug("security advisories fetch skipped: no token")
            return []

        parsed = _parse_owner_repo(canonical_url)
        if parsed is None:
            _logger.debug("security advisories fetch skipped: not a GitHub URL (%s)", canonical_url)
            return []
        owner, repo = parsed

        url = f"https://api.github.com/repos/{owner}/{repo}/security-advisories"
        items = _api_get_list(url, self._token)
        if items is None:
            return []

        advisories: list[SecurityAdvisory] = []
        for item in items:
            if item.get("withdrawn_at") is not None:
                continue
            advisory = _parse_advisory(item)
            if advisory is not None:
                advisories.append(advisory)
        return advisories[:ADVISORY_MAX_SUMMARIZED]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _qualifies(discussion: Discussion) -> bool:
    if discussion.category == "Q&A" and discussion.is_answered:
        return True
    if discussion.upvote_count + discussion.reaction_count >= DISCUSSION_MIN_ENGAGEMENT_SCORE:
        return True
    return discussion.comment_count >= DISCUSSION_MIN_REPLY_COUNT


def _ranking_key(discussion: Discussion) -> tuple[int, str]:
    score = discussion.upvote_count + discussion.reaction_count + discussion.comment_count
    return (score, discussion.updated_at)


def _parse_page(raw: object) -> tuple[list[Discussion], bool, str | None]:
    if not isinstance(raw, dict):
        raise TypeError("graphql response is not a JSON object")
    data = raw["data"]
    if not isinstance(data, dict):
        raise TypeError("graphql response missing 'data' object")
    repository = data["repository"]
    if not isinstance(repository, dict):
        raise TypeError("graphql response missing 'repository' object")
    discussions_obj = repository["discussions"]
    if not isinstance(discussions_obj, dict):
        raise TypeError("graphql response missing 'discussions' object")

    nodes_raw = discussions_obj["nodes"]
    if not isinstance(nodes_raw, list):
        raise TypeError("graphql response 'nodes' is not a list")
    nodes = [_parse_node(node) for node in nodes_raw]

    page_info = discussions_obj["pageInfo"]
    if not isinstance(page_info, dict):
        raise TypeError("graphql response missing 'pageInfo' object")
    has_next_page = bool(page_info["hasNextPage"])
    end_cursor = page_info.get("endCursor")
    end_cursor = str(end_cursor) if end_cursor is not None else None
    return nodes, has_next_page, end_cursor


def _parse_node(node: object) -> Discussion:
    if not isinstance(node, dict):
        raise TypeError("discussion node is not a JSON object")
    category_obj = node.get("category") or {}
    category = str(category_obj.get("name")) if isinstance(category_obj, dict) else ""
    answer_obj = node.get("answer")
    answer_body = (
        str(answer_obj.get("body"))
        if isinstance(answer_obj, dict) and answer_obj.get("body") is not None
        else None
    )
    reactions_obj = node.get("reactions") or {}
    reaction_count = (
        int(reactions_obj.get("totalCount", 0)) if isinstance(reactions_obj, dict) else 0
    )
    comments_obj = node.get("comments") or {}
    comment_count = int(comments_obj.get("totalCount", 0)) if isinstance(comments_obj, dict) else 0

    return Discussion(
        id=str(node["number"]),
        url=str(node["url"]),
        title=str(node.get("title", "")),
        body=str(node.get("body", "")),
        answer_body=answer_body,
        category=category,
        is_answered=node.get("answerChosenAt") is not None,
        upvote_count=int(node.get("upvoteCount", 0)),
        reaction_count=reaction_count,
        comment_count=comment_count,
        updated_at=str(node.get("updatedAt", "")),
    )


def _parse_owner_repo(canonical_url: str) -> tuple[str, str] | None:
    """Extract (owner, repo) from https://github.com/owner/repo."""
    m = re.match(r"^https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", canonical_url)
    if m is None:
        return None
    return m.group(1), m.group(2)


def _parse_linked_issues(pr_body: str) -> list[int]:
    """Extract issue numbers referenced with closes/fixes/resolves keywords."""
    return [int(m) for m in _ISSUE_REF_RE.findall(pr_body)]


def _api_get_list(url: str, token: str) -> list[dict[str, object]] | None:
    """GET a JSON array endpoint, returning only well-formed dict elements.

    Mirrors GithubRepoMetadataFetcher._api_get_dict's exact transport/header/
    exception-handling, but for endpoints returning a top-level JSON array
    (releases, security-advisories) rather than a single object.
    """
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {token}")
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
        _logger.warning("github api error for %s: %s", url, type(exc).__name__)
        return None
    if not isinstance(raw, list):
        _logger.warning("github api returned non-array payload for %s", url)
        return None
    return [item for item in raw if isinstance(item, dict)]


def _parse_release(item: dict[str, object]) -> Release | None:
    tag_name = item.get("tag_name")
    html_url = item.get("html_url")
    if not isinstance(tag_name, str) or not tag_name:
        return None
    if not isinstance(html_url, str) or not html_url:
        return None
    raw_name = item.get("name")
    name = raw_name if isinstance(raw_name, str) else None
    raw_body = item.get("body")
    body = raw_body if isinstance(raw_body, str) else None
    raw_published_at = item.get("published_at")
    published_at = raw_published_at if isinstance(raw_published_at, str) else None
    prerelease = bool(item.get("prerelease", False))
    return Release(
        tag_name=tag_name,
        name=name,
        body=body,
        html_url=html_url,
        published_at=published_at,
        prerelease=prerelease,
    )


def _parse_advisory(item: dict[str, object]) -> SecurityAdvisory | None:
    ghsa_id = item.get("ghsa_id")
    html_url = item.get("html_url")
    summary = item.get("summary")
    description = item.get("description")
    if not isinstance(ghsa_id, str) or not ghsa_id:
        return None
    if not isinstance(html_url, str) or not html_url:
        return None
    if not isinstance(summary, str) or not summary:
        return None
    if not isinstance(description, str) or not description:
        return None
    raw_cve_id = item.get("cve_id")
    cve_id = raw_cve_id if isinstance(raw_cve_id, str) else None
    raw_severity = item.get("severity")
    severity = raw_severity if isinstance(raw_severity, str) else ""
    raw_published_at = item.get("published_at")
    published_at = raw_published_at if isinstance(raw_published_at, str) else None
    return SecurityAdvisory(
        ghsa_id=ghsa_id,
        cve_id=cve_id,
        summary=summary,
        description=description,
        severity=severity,
        html_url=html_url,
        published_at=published_at,
    )


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
