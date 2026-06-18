"""Tests for GithubContextFetcher — RED phase.

All tests use a mock for urllib.request.urlopen so no network access is made.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from git_it.repository_ingestion.domain.github_context import GithubContext
from git_it.repository_ingestion.infrastructure.github import GithubContextFetcher
from git_it.repository_ingestion.infrastructure.sqlite import SqliteGithubContextCache

_CANONICAL_URL = "https://github.com/owner/repo"
_REPO_ID = "repo-abc"
_SHA = "a" * 40


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.sqlite3"


@pytest.fixture()
def cache(db_path: Path) -> SqliteGithubContextCache:
    c = SqliteGithubContextCache(db_path)
    c.initialize()
    return c


def _make_fetcher(
    cache: SqliteGithubContextCache, token: str | None = "tok"
) -> GithubContextFetcher:
    return GithubContextFetcher(cache=cache, token=token)


def _mock_response(data: object, status: int = 200) -> MagicMock:
    """Return a mock that behaves like urllib.request.urlopen context manager."""
    body = json.dumps(data).encode()
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _mock_http_error(code: int) -> Exception:
    import urllib.error

    return urllib.error.HTTPError(url="", code=code, msg="", hdrs=MagicMock(), fp=None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Test: no token → return None without any API call
# ---------------------------------------------------------------------------


def test_no_token_returns_none_without_api_call(cache: SqliteGithubContextCache) -> None:
    fetcher = _make_fetcher(cache, token=None)
    with patch("urllib.request.urlopen") as mock_open:
        result = fetcher.get_github_context(
            repository_id=_REPO_ID,
            canonical_url=_CANONICAL_URL,
            commit_sha=_SHA,
        )
    assert result is None
    mock_open.assert_not_called()


# ---------------------------------------------------------------------------
# Test: cache hit → return cached data without API call
# ---------------------------------------------------------------------------


def test_cache_hit_returns_cached_data_without_api_call(cache: SqliteGithubContextCache) -> None:
    ctx = GithubContext(pr_number=99, pr_title="Cached PR", has_pr=True)
    cache.save(_REPO_ID, _SHA, ctx)
    fetcher = _make_fetcher(cache)
    with patch("urllib.request.urlopen") as mock_open:
        result = fetcher.get_github_context(
            repository_id=_REPO_ID,
            canonical_url=_CANONICAL_URL,
            commit_sha=_SHA,
        )
    mock_open.assert_not_called()
    assert result is not None
    assert result.pr_number == 99


# ---------------------------------------------------------------------------
# Test: API returns empty array → save negative cache entry, return None
# ---------------------------------------------------------------------------


def test_api_no_pr_saves_negative_cache_and_returns_none(
    cache: SqliteGithubContextCache,
) -> None:
    fetcher = _make_fetcher(cache)
    with patch("urllib.request.urlopen", return_value=_mock_response([])):
        result = fetcher.get_github_context(
            repository_id=_REPO_ID,
            canonical_url=_CANONICAL_URL,
            commit_sha=_SHA,
        )
    assert result is None
    # Negative cache entry must have been written.
    assert cache.is_cached(_REPO_ID, _SHA) is True
    assert cache.get_cached(_REPO_ID, _SHA) is None


# ---------------------------------------------------------------------------
# Test: API returns PR → save positive cache entry, return GithubContext
# ---------------------------------------------------------------------------


def test_api_pr_found_saves_positive_cache_and_returns_context(
    cache: SqliteGithubContextCache,
) -> None:
    pr_payload = [
        {
            "number": 42,
            "title": "Add login feature",
            "body": "Fixes #10\n\nAdds OAuth login.",
        }
    ]
    issue_payload = {"body": "Issue 10 body text"}

    def _urlopen_side_effect(req: object, timeout: int = 10) -> MagicMock:
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/pulls" in url:
            return _mock_response(pr_payload)
        # issue fetch
        return _mock_response(issue_payload)

    fetcher = _make_fetcher(cache)
    with patch("urllib.request.urlopen", side_effect=_urlopen_side_effect):
        result = fetcher.get_github_context(
            repository_id=_REPO_ID,
            canonical_url=_CANONICAL_URL,
            commit_sha=_SHA,
        )
    assert result is not None
    assert result.pr_number == 42
    assert result.pr_title == "Add login feature"
    assert result.has_pr is True
    # Must also be cached now.
    assert cache.is_cached(_REPO_ID, _SHA) is True
    cached = cache.get_cached(_REPO_ID, _SHA)
    assert cached is not None
    assert cached.pr_number == 42


# ---------------------------------------------------------------------------
# Test: 429 rate limit → skip without caching
# ---------------------------------------------------------------------------


def test_rate_limit_429_skips_without_writing_cache(cache: SqliteGithubContextCache) -> None:
    fetcher = _make_fetcher(cache)
    with patch("urllib.request.urlopen", side_effect=_mock_http_error(429)):
        result = fetcher.get_github_context(
            repository_id=_REPO_ID,
            canonical_url=_CANONICAL_URL,
            commit_sha=_SHA,
        )
    assert result is None
    # Must NOT write a cache entry for a transient error.
    assert cache.is_cached(_REPO_ID, _SHA) is False


# ---------------------------------------------------------------------------
# Test: 403 forbidden → skip without caching
# ---------------------------------------------------------------------------


def test_forbidden_403_skips_without_writing_cache(cache: SqliteGithubContextCache) -> None:
    fetcher = _make_fetcher(cache)
    with patch("urllib.request.urlopen", side_effect=_mock_http_error(403)):
        result = fetcher.get_github_context(
            repository_id=_REPO_ID,
            canonical_url=_CANONICAL_URL,
            commit_sha=_SHA,
        )
    assert result is None
    assert cache.is_cached(_REPO_ID, _SHA) is False


# ---------------------------------------------------------------------------
# Test: 401 unauthorized → return None without caching
# ---------------------------------------------------------------------------


def test_unauthorized_401_returns_none_without_caching(cache: SqliteGithubContextCache) -> None:
    fetcher = _make_fetcher(cache)
    with patch("urllib.request.urlopen", side_effect=_mock_http_error(401)):
        result = fetcher.get_github_context(
            repository_id=_REPO_ID,
            canonical_url=_CANONICAL_URL,
            commit_sha=_SHA,
        )
    assert result is None
    assert cache.is_cached(_REPO_ID, _SHA) is False


# ---------------------------------------------------------------------------
# Test: network timeout → skip without caching
# ---------------------------------------------------------------------------


def test_network_timeout_skips_without_writing_cache(cache: SqliteGithubContextCache) -> None:
    fetcher = _make_fetcher(cache)
    with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
        result = fetcher.get_github_context(
            repository_id=_REPO_ID,
            canonical_url=_CANONICAL_URL,
            commit_sha=_SHA,
        )
    assert result is None
    assert cache.is_cached(_REPO_ID, _SHA) is False


# ---------------------------------------------------------------------------
# Test: issue fetch failure → skip that issue only, proceed with rest
# ---------------------------------------------------------------------------


def test_issue_fetch_failure_skips_that_issue_only(cache: SqliteGithubContextCache) -> None:
    """If issue fetch fails for one issue, others still appear in the result."""
    pr_payload = [
        {
            "number": 5,
            "title": "Multi-issue PR",
            "body": "Fixes #1\nCloses #2",
        }
    ]

    call_count = [0]

    def _urlopen_side_effect(req: object, timeout: int = 10) -> MagicMock:
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/pulls" in url:
            return _mock_response(pr_payload)
        call_count[0] += 1
        if call_count[0] == 1:
            # First issue fetch fails.
            raise _mock_http_error(404)
        # Second succeeds.
        return _mock_response({"body": "Issue 2 body"})

    fetcher = _make_fetcher(cache)
    with patch("urllib.request.urlopen", side_effect=_urlopen_side_effect):
        result = fetcher.get_github_context(
            repository_id=_REPO_ID,
            canonical_url=_CANONICAL_URL,
            commit_sha=_SHA,
        )
    # PR context must still be returned with at least one issue body.
    assert result is not None
    assert result.pr_number == 5
    assert len(result.issue_bodies) >= 1
    assert "Issue 2 body" in result.issue_bodies
