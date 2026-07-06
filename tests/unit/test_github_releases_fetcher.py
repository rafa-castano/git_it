"""Tests for GithubReleasesFetcher — RED phase (spec 026).

All tests mock urllib.request.urlopen so no network access is made, mirroring
the existing pattern in test_github_repo_metadata_fetcher.py /
test_github_discussions_fetcher.py (this codebase's GitHub adapter uses stdlib
urllib, not httpx/respx).
"""

import json
import urllib.error
from typing import Any
from unittest.mock import MagicMock, patch

from git_it.repository_ingestion.domain.releases import Release
from git_it.repository_ingestion.infrastructure.github import GithubReleasesFetcher

_CANONICAL_URL = "https://github.com/owner/repo"


def _release_item(
    *,
    tag_name: str = "v1.0.0",
    name: str | None = "v1.0.0",
    body: str | None = "Release notes",
    html_url: str = "https://github.com/owner/repo/releases/tag/v1.0.0",
    published_at: str | None = "2026-01-01T00:00:00Z",
    prerelease: bool = False,
    draft: bool = False,
) -> dict[str, Any]:
    return {
        "tag_name": tag_name,
        "name": name,
        "body": body,
        "html_url": html_url,
        "published_at": published_at,
        "prerelease": prerelease,
        "draft": draft,
    }


def _mock_response(data: object) -> MagicMock:
    body = json.dumps(data).encode()
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _mock_http_error(code: int) -> Exception:
    return urllib.error.HTTPError(url="", code=code, msg="", hdrs=MagicMock(), fp=None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Test: no token -> [] without any API call
# ---------------------------------------------------------------------------


def test_no_token_returns_empty_list_without_api_call() -> None:
    fetcher = GithubReleasesFetcher(token=None)
    with patch("urllib.request.urlopen") as mock_open:
        result = fetcher.fetch_releases(_CANONICAL_URL)
    assert result == []
    mock_open.assert_not_called()


# ---------------------------------------------------------------------------
# Test: non-GitHub URL -> [] without any API call
# ---------------------------------------------------------------------------


def test_non_github_url_returns_empty_list_without_api_call() -> None:
    fetcher = GithubReleasesFetcher(token="tok")
    with patch("urllib.request.urlopen") as mock_open:
        result = fetcher.fetch_releases("https://gitlab.com/owner/repo")
    assert result == []
    mock_open.assert_not_called()


# ---------------------------------------------------------------------------
# Test: happy path -> 2 releases returned with correct fields
# ---------------------------------------------------------------------------


def test_happy_path_returns_releases() -> None:
    fetcher = GithubReleasesFetcher(token="tok")
    payload = [
        _release_item(
            tag_name="v2.0.0",
            name="v2.0.0",
            html_url="https://github.com/owner/repo/releases/tag/v2.0.0",
        ),
        _release_item(
            tag_name="v1.0.0",
            name="v1.0.0",
            html_url="https://github.com/owner/repo/releases/tag/v1.0.0",
        ),
    ]
    with patch("urllib.request.urlopen", return_value=_mock_response(payload)):
        result = fetcher.fetch_releases(_CANONICAL_URL)
    assert result == [
        Release(
            tag_name="v2.0.0",
            name="v2.0.0",
            body="Release notes",
            html_url="https://github.com/owner/repo/releases/tag/v2.0.0",
            published_at="2026-01-01T00:00:00Z",
            prerelease=False,
        ),
        Release(
            tag_name="v1.0.0",
            name="v1.0.0",
            body="Release notes",
            html_url="https://github.com/owner/repo/releases/tag/v1.0.0",
            published_at="2026-01-01T00:00:00Z",
            prerelease=False,
        ),
    ]


# ---------------------------------------------------------------------------
# Test: draft releases excluded, prereleases included
# ---------------------------------------------------------------------------


def test_draft_excluded_prerelease_included() -> None:
    fetcher = GithubReleasesFetcher(token="tok")
    payload = [
        _release_item(tag_name="v1.0.0-draft", draft=True),
        _release_item(tag_name="v1.0.0-rc1", prerelease=True, draft=False),
    ]
    with patch("urllib.request.urlopen", return_value=_mock_response(payload)):
        result = fetcher.fetch_releases(_CANONICAL_URL)
    assert [r.tag_name for r in result] == ["v1.0.0-rc1"]
    assert result[0].prerelease is True


# ---------------------------------------------------------------------------
# Test: RELEASE_MAX_SUMMARIZED bound respected
# ---------------------------------------------------------------------------


def test_max_summarized_bound_respected() -> None:
    fetcher = GithubReleasesFetcher(token="tok")
    payload = [_release_item(tag_name=f"v{i}.0.0") for i in range(5)]
    with (
        patch("git_it.repository_ingestion.infrastructure.github.RELEASE_MAX_SUMMARIZED", 2),
        patch("urllib.request.urlopen", return_value=_mock_response(payload)),
    ):
        result = fetcher.fetch_releases(_CANONICAL_URL)
    assert len(result) == 2
    assert [r.tag_name for r in result] == ["v0.0.0", "v1.0.0"]


# ---------------------------------------------------------------------------
# Test: HTTP error -> [] gracefully
# ---------------------------------------------------------------------------


def test_http_error_returns_empty_list() -> None:
    fetcher = GithubReleasesFetcher(token="tok")
    with patch("urllib.request.urlopen", side_effect=_mock_http_error(500)):
        result = fetcher.fetch_releases(_CANONICAL_URL)
    assert result == []


# ---------------------------------------------------------------------------
# Test: non-array payload -> [] gracefully
# ---------------------------------------------------------------------------


def test_non_array_payload_returns_empty_list() -> None:
    fetcher = GithubReleasesFetcher(token="tok")
    with patch("urllib.request.urlopen", return_value=_mock_response({"not": "a list"})):
        result = fetcher.fetch_releases(_CANONICAL_URL)
    assert result == []


# ---------------------------------------------------------------------------
# Test: malformed item (missing required field) is skipped, others kept
# ---------------------------------------------------------------------------


def test_malformed_item_is_skipped() -> None:
    fetcher = GithubReleasesFetcher(token="tok")
    good = _release_item(tag_name="v1.0.0")
    bad_missing_tag = _release_item(
        tag_name="", html_url="https://github.com/owner/repo/releases/tag/bad"
    )
    bad_missing_url = {**_release_item(tag_name="v3.0.0"), "html_url": ""}
    payload = [good, bad_missing_tag, bad_missing_url]
    with patch("urllib.request.urlopen", return_value=_mock_response(payload)):
        result = fetcher.fetch_releases(_CANONICAL_URL)
    assert [r.tag_name for r in result] == ["v1.0.0"]


# ---------------------------------------------------------------------------
# Test: malformed JSON body -> [] gracefully
# ---------------------------------------------------------------------------


def test_malformed_json_returns_empty_list() -> None:
    fetcher = GithubReleasesFetcher(token="tok")
    resp = MagicMock()
    resp.read.return_value = b"not json{{{"
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=resp):
        result = fetcher.fetch_releases(_CANONICAL_URL)
    assert result == []
