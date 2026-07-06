"""Tests for GithubSecurityAdvisoriesFetcher — RED phase (spec 026).

All tests mock urllib.request.urlopen so no network access is made, mirroring
the existing pattern in test_github_repo_metadata_fetcher.py /
test_github_discussions_fetcher.py (this codebase's GitHub adapter uses stdlib
urllib, not httpx/respx).
"""

import json
import urllib.error
from typing import Any
from unittest.mock import MagicMock, patch

from git_it.repository_ingestion.domain.advisories import SecurityAdvisory
from git_it.repository_ingestion.infrastructure.github import GithubSecurityAdvisoriesFetcher

_CANONICAL_URL = "https://github.com/owner/repo"


def _advisory_item(
    *,
    ghsa_id: str = "GHSA-aaaa-bbbb-cccc",
    cve_id: str | None = "CVE-2026-0001",
    summary: str = "A SQL injection vulnerability",
    description: str = "Full description of the vulnerability",
    severity: str = "high",
    html_url: str = "https://github.com/owner/repo/security/advisories/GHSA-aaaa-bbbb-cccc",
    published_at: str | None = "2026-01-01T00:00:00Z",
    withdrawn_at: str | None = None,
) -> dict[str, Any]:
    return {
        "ghsa_id": ghsa_id,
        "cve_id": cve_id,
        "summary": summary,
        "description": description,
        "severity": severity,
        "html_url": html_url,
        "published_at": published_at,
        "withdrawn_at": withdrawn_at,
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
    fetcher = GithubSecurityAdvisoriesFetcher(token=None)
    with patch("urllib.request.urlopen") as mock_open:
        result = fetcher.fetch_advisories(_CANONICAL_URL)
    assert result == []
    mock_open.assert_not_called()


# ---------------------------------------------------------------------------
# Test: non-GitHub URL -> [] without any API call
# ---------------------------------------------------------------------------


def test_non_github_url_returns_empty_list_without_api_call() -> None:
    fetcher = GithubSecurityAdvisoriesFetcher(token="tok")
    with patch("urllib.request.urlopen") as mock_open:
        result = fetcher.fetch_advisories("https://gitlab.com/owner/repo")
    assert result == []
    mock_open.assert_not_called()


# ---------------------------------------------------------------------------
# Test: happy path -> 2 advisories returned with correct fields
# ---------------------------------------------------------------------------


def test_happy_path_returns_advisories() -> None:
    fetcher = GithubSecurityAdvisoriesFetcher(token="tok")
    payload = [
        _advisory_item(
            ghsa_id="GHSA-aaaa-bbbb-cccc",
            html_url="https://github.com/owner/repo/security/advisories/GHSA-aaaa-bbbb-cccc",
        ),
        _advisory_item(
            ghsa_id="GHSA-dddd-eeee-ffff",
            html_url="https://github.com/owner/repo/security/advisories/GHSA-dddd-eeee-ffff",
            severity="critical",
        ),
    ]
    with patch("urllib.request.urlopen", return_value=_mock_response(payload)):
        result = fetcher.fetch_advisories(_CANONICAL_URL)
    assert result == [
        SecurityAdvisory(
            ghsa_id="GHSA-aaaa-bbbb-cccc",
            cve_id="CVE-2026-0001",
            summary="A SQL injection vulnerability",
            description="Full description of the vulnerability",
            severity="high",
            html_url="https://github.com/owner/repo/security/advisories/GHSA-aaaa-bbbb-cccc",
            published_at="2026-01-01T00:00:00Z",
        ),
        SecurityAdvisory(
            ghsa_id="GHSA-dddd-eeee-ffff",
            cve_id="CVE-2026-0001",
            summary="A SQL injection vulnerability",
            description="Full description of the vulnerability",
            severity="critical",
            html_url="https://github.com/owner/repo/security/advisories/GHSA-dddd-eeee-ffff",
            published_at="2026-01-01T00:00:00Z",
        ),
    ]


# ---------------------------------------------------------------------------
# Test: withdrawn advisory excluded
# ---------------------------------------------------------------------------


def test_withdrawn_advisory_excluded() -> None:
    fetcher = GithubSecurityAdvisoriesFetcher(token="tok")
    payload = [
        _advisory_item(ghsa_id="GHSA-aaaa-bbbb-cccc", withdrawn_at="2026-02-01T00:00:00Z"),
        _advisory_item(ghsa_id="GHSA-dddd-eeee-ffff", withdrawn_at=None),
    ]
    with patch("urllib.request.urlopen", return_value=_mock_response(payload)):
        result = fetcher.fetch_advisories(_CANONICAL_URL)
    assert [a.ghsa_id for a in result] == ["GHSA-dddd-eeee-ffff"]


# ---------------------------------------------------------------------------
# Test: ADVISORY_MAX_SUMMARIZED bound respected
# ---------------------------------------------------------------------------


def test_max_summarized_bound_respected() -> None:
    fetcher = GithubSecurityAdvisoriesFetcher(token="tok")
    payload = [
        _advisory_item(
            ghsa_id=f"GHSA-aaaa-bbbb-000{i}",
            html_url=f"https://github.com/owner/repo/security/advisories/GHSA-aaaa-bbbb-000{i}",
        )
        for i in range(5)
    ]
    with (
        patch("git_it.repository_ingestion.infrastructure.github.ADVISORY_MAX_SUMMARIZED", 2),
        patch("urllib.request.urlopen", return_value=_mock_response(payload)),
    ):
        result = fetcher.fetch_advisories(_CANONICAL_URL)
    assert len(result) == 2
    assert [a.ghsa_id for a in result] == ["GHSA-aaaa-bbbb-0000", "GHSA-aaaa-bbbb-0001"]


# ---------------------------------------------------------------------------
# Test: HTTP error -> [] gracefully
# ---------------------------------------------------------------------------


def test_http_error_returns_empty_list() -> None:
    fetcher = GithubSecurityAdvisoriesFetcher(token="tok")
    with patch("urllib.request.urlopen", side_effect=_mock_http_error(500)):
        result = fetcher.fetch_advisories(_CANONICAL_URL)
    assert result == []


# ---------------------------------------------------------------------------
# Test: non-array payload -> [] gracefully
# ---------------------------------------------------------------------------


def test_non_array_payload_returns_empty_list() -> None:
    fetcher = GithubSecurityAdvisoriesFetcher(token="tok")
    with patch("urllib.request.urlopen", return_value=_mock_response({"not": "a list"})):
        result = fetcher.fetch_advisories(_CANONICAL_URL)
    assert result == []


# ---------------------------------------------------------------------------
# Test: malformed item (missing required field) is skipped, others kept
# ---------------------------------------------------------------------------


def test_malformed_item_is_skipped() -> None:
    fetcher = GithubSecurityAdvisoriesFetcher(token="tok")
    good = _advisory_item(ghsa_id="GHSA-aaaa-bbbb-cccc")
    bad_missing_ghsa_id = _advisory_item(ghsa_id="")
    bad_missing_summary = {**_advisory_item(ghsa_id="GHSA-zzzz-yyyy-xxxx"), "summary": ""}
    payload = [good, bad_missing_ghsa_id, bad_missing_summary]
    with patch("urllib.request.urlopen", return_value=_mock_response(payload)):
        result = fetcher.fetch_advisories(_CANONICAL_URL)
    assert [a.ghsa_id for a in result] == ["GHSA-aaaa-bbbb-cccc"]


# ---------------------------------------------------------------------------
# Test: malformed JSON body -> [] gracefully
# ---------------------------------------------------------------------------


def test_malformed_json_returns_empty_list() -> None:
    fetcher = GithubSecurityAdvisoriesFetcher(token="tok")
    resp = MagicMock()
    resp.read.return_value = b"not json{{{"
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=resp):
        result = fetcher.fetch_advisories(_CANONICAL_URL)
    assert result == []
