"""Tests for GithubCommitAuthorsFetcher — resolves commit-author GitHub logins (spec 031).

All tests mock urllib.request.urlopen so no network access is made, mirroring the
existing pattern in test_github_repo_metadata_fetcher.py (this codebase's GitHub
adapters use stdlib urllib, not httpx, so respx does not apply here).
"""

import json
import urllib.error
from collections.abc import Callable
from unittest.mock import MagicMock, patch

from git_it.repository_ingestion.infrastructure.github import (
    GithubCommitAuthorsFetcher,
    _is_valid_github_login,
)

_CANONICAL_URL = "https://github.com/owner/repo"


def _mock_response(data: object) -> MagicMock:
    body = json.dumps(data).encode()
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _mock_http_error(code: int) -> Exception:
    return urllib.error.HTTPError(url="", code=code, msg="", hdrs=MagicMock(), fp=None)  # type: ignore[arg-type]


def _commit(email: str, login: str | None) -> dict[str, object]:
    """Build one List-commits array element.

    ``login is None`` models GitHub failing to match the commit email to an
    account: the top-level ``author`` object is ``null``.
    """
    return {
        "sha": "deadbeef",
        "commit": {"author": {"name": "Someone", "email": email}},
        "author": None if login is None else {"login": login},
    }


def _pages_side_effect(pages: list[list[dict[str, object]]]) -> Callable[..., MagicMock]:
    """Return a urlopen side effect that serves ``pages[page-1]`` per ?page= query."""

    def _side_effect(req: object, timeout: int = 10) -> MagicMock:
        url = req.full_url if hasattr(req, "full_url") else str(req)
        page = _page_of(url)
        payload = pages[page - 1] if page - 1 < len(pages) else []
        return _mock_response(payload)

    return _side_effect


def _page_of(url: str) -> int:
    """Extract the ?page= query value (guarding against the 'per_page=' substring)."""
    if "&page=" in url:
        return int(url.split("&page=")[1].split("&")[0])
    return 1


# ---------------------------------------------------------------------------
# No token / empty needed / non-GitHub URL -> {} without any API call
# ---------------------------------------------------------------------------


def test_no_token_returns_empty_without_api_call() -> None:
    fetcher = GithubCommitAuthorsFetcher(token=None)
    with patch("urllib.request.urlopen") as mock_open:
        result = fetcher.fetch_author_logins(_CANONICAL_URL, {"a@example.com"})
    assert result == {}
    mock_open.assert_not_called()


def test_empty_needed_returns_empty_without_api_call() -> None:
    fetcher = GithubCommitAuthorsFetcher(token="tok")
    with patch("urllib.request.urlopen") as mock_open:
        result = fetcher.fetch_author_logins(_CANONICAL_URL, set())
    assert result == {}
    mock_open.assert_not_called()


def test_non_github_url_returns_empty_without_api_call() -> None:
    fetcher = GithubCommitAuthorsFetcher(token="tok")
    with patch("urllib.request.urlopen") as mock_open:
        result = fetcher.fetch_author_logins("https://gitlab.com/owner/repo", {"a@example.com"})
    assert result == {}
    mock_open.assert_not_called()


# ---------------------------------------------------------------------------
# Happy path: maps commit.author.email -> author.login
# ---------------------------------------------------------------------------


def test_maps_email_to_login_for_matched_account() -> None:
    fetcher = GithubCommitAuthorsFetcher(token="tok")
    pages = [[_commit("alice@example.com", "alice-gh")]]
    with patch("urllib.request.urlopen", side_effect=_pages_side_effect(pages)):
        result = fetcher.fetch_author_logins(_CANONICAL_URL, {"alice@example.com"})
    assert result == {"alice@example.com": "alice-gh"}


# ---------------------------------------------------------------------------
# Skips commits whose top-level author is null (GitHub couldn't match)
# ---------------------------------------------------------------------------


def test_skips_commit_with_null_top_level_author() -> None:
    fetcher = GithubCommitAuthorsFetcher(token="tok")
    pages = [[_commit("nomatch@example.com", None)]]
    with patch("urllib.request.urlopen", side_effect=_pages_side_effect(pages)):
        result = fetcher.fetch_author_logins(_CANONICAL_URL, {"nomatch@example.com"})
    assert result == {}


# ---------------------------------------------------------------------------
# Restricts resolution to needed_emails only
# ---------------------------------------------------------------------------


def test_restricts_to_needed_emails() -> None:
    fetcher = GithubCommitAuthorsFetcher(token="tok")
    pages = [
        [
            _commit("alice@example.com", "alice-gh"),
            _commit("bob@example.com", "bob-gh"),
        ]
    ]
    with patch("urllib.request.urlopen", side_effect=_pages_side_effect(pages)):
        result = fetcher.fetch_author_logins(_CANONICAL_URL, {"alice@example.com"})
    assert result == {"alice@example.com": "alice-gh"}


# ---------------------------------------------------------------------------
# Stops early once every needed email is resolved (no wasted page fetch)
# ---------------------------------------------------------------------------


def test_stops_early_when_all_needed_resolved() -> None:
    fetcher = GithubCommitAuthorsFetcher(token="tok")
    # A full first page (100 entries) resolves the only needed email; a second
    # page exists but must NOT be requested.
    first_page = [_commit("alice@example.com", "alice-gh")] + [
        _commit(f"filler{i}@example.com", f"filler{i}") for i in range(99)
    ]
    second_page = [_commit("late@example.com", "late-gh")]
    calls: list[str] = []

    def _side_effect(req: object, timeout: int = 10) -> MagicMock:
        url = req.full_url if hasattr(req, "full_url") else str(req)
        calls.append(url)
        payload = first_page if _page_of(url) == 1 else second_page
        return _mock_response(payload)

    with patch("urllib.request.urlopen", side_effect=_side_effect):
        result = fetcher.fetch_author_logins(_CANONICAL_URL, {"alice@example.com"})
    assert result == {"alice@example.com": "alice-gh"}
    assert len(calls) == 1  # second page never requested


# ---------------------------------------------------------------------------
# Paginates across multiple pages when needed emails span pages
# ---------------------------------------------------------------------------


def test_paginates_across_pages() -> None:
    fetcher = GithubCommitAuthorsFetcher(token="tok")
    first_page = [_commit("alice@example.com", "alice-gh")] + [
        _commit(f"filler{i}@example.com", f"filler{i}") for i in range(99)
    ]
    second_page = [_commit("bob@example.com", "bob-gh")]
    with patch(
        "urllib.request.urlopen",
        side_effect=_pages_side_effect([first_page, second_page]),
    ):
        result = fetcher.fetch_author_logins(
            _CANONICAL_URL, {"alice@example.com", "bob@example.com"}
        )
    assert result == {"alice@example.com": "alice-gh", "bob@example.com": "bob-gh"}


# ---------------------------------------------------------------------------
# Error handling: HTTP error -> partial (or empty) result, never raises
# ---------------------------------------------------------------------------


def test_http_error_returns_empty_without_raising() -> None:
    fetcher = GithubCommitAuthorsFetcher(token="tok")
    with patch("urllib.request.urlopen", side_effect=_mock_http_error(500)):
        result = fetcher.fetch_author_logins(_CANONICAL_URL, {"alice@example.com"})
    assert result == {}


def test_error_on_second_page_returns_partial() -> None:
    fetcher = GithubCommitAuthorsFetcher(token="tok")
    first_page = [_commit("alice@example.com", "alice-gh")] + [
        _commit(f"filler{i}@example.com", f"filler{i}") for i in range(99)
    ]

    def _side_effect(req: object, timeout: int = 10) -> MagicMock:
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if _page_of(url) == 1:
            return _mock_response(first_page)
        raise _mock_http_error(429)

    with patch("urllib.request.urlopen", side_effect=_side_effect):
        result = fetcher.fetch_author_logins(
            _CANONICAL_URL, {"alice@example.com", "bob@example.com"}
        )
    assert result == {"alice@example.com": "alice-gh"}


def test_malformed_payload_returns_empty() -> None:
    fetcher = GithubCommitAuthorsFetcher(token="tok")
    with patch("urllib.request.urlopen", return_value=_mock_response({"not": "a list"})):
        result = fetcher.fetch_author_logins(_CANONICAL_URL, {"alice@example.com"})
    assert result == {}


# ---------------------------------------------------------------------------
# AC-09: a hostile login string is rejected (charset-validated before use)
# ---------------------------------------------------------------------------


def test_hostile_login_is_rejected() -> None:
    fetcher = GithubCommitAuthorsFetcher(token="tok")
    hostile = '"><img src=x onerror=alert(1)>'
    pages = [[_commit("evil@example.com", hostile)]]
    with patch("urllib.request.urlopen", side_effect=_pages_side_effect(pages)):
        result = fetcher.fetch_author_logins(_CANONICAL_URL, {"evil@example.com"})
    assert result == {}


def test_login_charset_validator_accepts_valid_and_rejects_hostile() -> None:
    assert _is_valid_github_login("octocat")
    assert _is_valid_github_login("a-valid-login-123")
    assert not _is_valid_github_login("has space")
    assert not _is_valid_github_login("bad/slash")
    assert not _is_valid_github_login('"><script>')
    assert not _is_valid_github_login("")
    assert not _is_valid_github_login("x" * 40)  # exceeds GitHub's 39-char cap
    assert not _is_valid_github_login(None)
