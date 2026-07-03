"""Tests for GithubRepoMetadataFetcher — RED phase.

All tests mock urllib.request.urlopen so no network access is made, mirroring
the existing pattern in test_github_api_fetcher.py (this codebase's GitHub
adapter uses stdlib urllib, not httpx, so respx does not apply here — see
specs/019-github-stars-languages.md § Tests required for the full rationale).
"""

import json
import urllib.error
from collections.abc import Callable
from unittest.mock import MagicMock, patch

from git_it.repository_ingestion.domain.repo_metadata import LanguageBreakdown, RepoMetadata
from git_it.repository_ingestion.infrastructure.github import GithubRepoMetadataFetcher

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


def _urlopen_side_effect(
    repo_payload: object, languages_payload: object
) -> Callable[..., MagicMock]:
    def _side_effect(req: object, timeout: int = 10) -> MagicMock:
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url.endswith("/languages"):
            return _mock_response(languages_payload)
        return _mock_response(repo_payload)

    return _side_effect


# ---------------------------------------------------------------------------
# Test: no token -> return None without any API call
# ---------------------------------------------------------------------------


def test_no_token_returns_none_without_api_call() -> None:
    fetcher = GithubRepoMetadataFetcher(token=None)
    with patch("urllib.request.urlopen") as mock_open:
        result = fetcher.fetch_repo_metadata(_CANONICAL_URL)
    assert result is None
    mock_open.assert_not_called()


# ---------------------------------------------------------------------------
# Test: non-GitHub URL -> return None without any API call
# ---------------------------------------------------------------------------


def test_non_github_url_returns_none_without_api_call() -> None:
    fetcher = GithubRepoMetadataFetcher(token="tok")
    with patch("urllib.request.urlopen") as mock_open:
        result = fetcher.fetch_repo_metadata("https://gitlab.com/owner/repo")
    assert result is None
    mock_open.assert_not_called()


# ---------------------------------------------------------------------------
# Test: happy path -> stars + languages both returned
# ---------------------------------------------------------------------------


def test_happy_path_returns_stars_and_languages() -> None:
    fetcher = GithubRepoMetadataFetcher(token="tok")
    repo_payload = {"stargazers_count": 1234}
    languages_payload = {"Python": 300, "HTML": 100}
    with patch(
        "urllib.request.urlopen",
        side_effect=_urlopen_side_effect(repo_payload, languages_payload),
    ):
        result = fetcher.fetch_repo_metadata(_CANONICAL_URL)
    assert result == RepoMetadata(
        stars=1234,
        languages=(
            LanguageBreakdown(language="Python", bytes=300),
            LanguageBreakdown(language="HTML", bytes=100),
        ),
    )


# ---------------------------------------------------------------------------
# Test: stars HTTP error -> whole result is None
# ---------------------------------------------------------------------------


def test_stars_http_error_returns_none() -> None:
    fetcher = GithubRepoMetadataFetcher(token="tok")
    with patch("urllib.request.urlopen", side_effect=_mock_http_error(404)):
        result = fetcher.fetch_repo_metadata(_CANONICAL_URL)
    assert result is None


# ---------------------------------------------------------------------------
# Test: stars malformed JSON -> whole result is None
# ---------------------------------------------------------------------------


def test_stars_malformed_json_returns_none() -> None:
    fetcher = GithubRepoMetadataFetcher(token="tok")
    resp = MagicMock()
    resp.read.return_value = b"not json{{{"
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=resp):
        result = fetcher.fetch_repo_metadata(_CANONICAL_URL)
    assert result is None


# ---------------------------------------------------------------------------
# Test: stars payload is not a JSON object -> whole result is None
# ---------------------------------------------------------------------------


def test_stars_non_dict_json_returns_none() -> None:
    fetcher = GithubRepoMetadataFetcher(token="tok")
    with patch("urllib.request.urlopen", return_value=_mock_response([1, 2, 3])):
        result = fetcher.fetch_repo_metadata(_CANONICAL_URL)
    assert result is None


# ---------------------------------------------------------------------------
# Test: stargazers_count missing/non-int -> whole result is None
# ---------------------------------------------------------------------------


def test_stars_missing_stargazers_count_returns_none() -> None:
    fetcher = GithubRepoMetadataFetcher(token="tok")
    with patch("urllib.request.urlopen", return_value=_mock_response({"name": "repo"})):
        result = fetcher.fetch_repo_metadata(_CANONICAL_URL)
    assert result is None


# ---------------------------------------------------------------------------
# Test: languages HTTP error -> stars kept, languages empty
# ---------------------------------------------------------------------------


def test_languages_http_error_keeps_stars_with_empty_languages() -> None:
    fetcher = GithubRepoMetadataFetcher(token="tok")
    repo_payload = {"stargazers_count": 42}

    def _side_effect(req: object, timeout: int = 10) -> MagicMock:
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url.endswith("/languages"):
            raise _mock_http_error(500)
        return _mock_response(repo_payload)

    with patch("urllib.request.urlopen", side_effect=_side_effect):
        result = fetcher.fetch_repo_metadata(_CANONICAL_URL)
    assert result == RepoMetadata(stars=42, languages=())


# ---------------------------------------------------------------------------
# Test: malformed language entries dropped, valid ones kept
# ---------------------------------------------------------------------------


def test_malformed_language_entries_are_dropped() -> None:
    fetcher = GithubRepoMetadataFetcher(token="tok")
    repo_payload = {"stargazers_count": 5}
    languages_payload = {
        "Python": 300,
        "Weird": -10,
        "Bad": "not-a-number",
        "Good": 50,
    }
    with patch(
        "urllib.request.urlopen",
        side_effect=_urlopen_side_effect(repo_payload, languages_payload),
    ):
        result = fetcher.fetch_repo_metadata(_CANONICAL_URL)
    assert result is not None
    assert set(result.languages) == {
        LanguageBreakdown(language="Python", bytes=300),
        LanguageBreakdown(language="Good", bytes=50),
    }


# ---------------------------------------------------------------------------
# Test: empty languages payload -> languages=()
# ---------------------------------------------------------------------------


def test_empty_languages_payload_returns_empty_tuple() -> None:
    fetcher = GithubRepoMetadataFetcher(token="tok")
    repo_payload = {"stargazers_count": 7}
    with patch(
        "urllib.request.urlopen",
        side_effect=_urlopen_side_effect(repo_payload, {}),
    ):
        result = fetcher.fetch_repo_metadata(_CANONICAL_URL)
    assert result == RepoMetadata(stars=7, languages=())


# ---------------------------------------------------------------------------
# Test: languages payload not a dict -> languages=()
# ---------------------------------------------------------------------------


def test_languages_non_dict_payload_returns_empty_tuple() -> None:
    fetcher = GithubRepoMetadataFetcher(token="tok")
    repo_payload = {"stargazers_count": 7}
    with patch(
        "urllib.request.urlopen",
        side_effect=_urlopen_side_effect(repo_payload, [1, 2, 3]),
    ):
        result = fetcher.fetch_repo_metadata(_CANONICAL_URL)
    assert result == RepoMetadata(stars=7, languages=())
