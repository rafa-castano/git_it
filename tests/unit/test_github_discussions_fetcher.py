"""Tests for GithubDiscussionsFetcher — RED phase (spec 022).

All tests mock urllib.request.urlopen so no network access is made, mirroring
the existing pattern in test_github_api_fetcher.py / test_github_repo_metadata_fetcher.py
(this codebase's GitHub adapter uses stdlib urllib, not httpx).
"""

import json
import urllib.error
from typing import Any
from unittest.mock import MagicMock, patch

from git_it.repository_ingestion.domain.discussions import Discussion
from git_it.repository_ingestion.infrastructure.github import GithubDiscussionsFetcher

_CANONICAL_URL = "https://github.com/owner/repo"


def _discussion_node(
    *,
    number: int = 1,
    title: str = "Discussion title",
    body: str = "Discussion body",
    category: str = "General",
    answer_chosen_at: str | None = None,
    upvote_count: int = 0,
    reaction_count: int = 0,
    comment_count: int = 0,
    updated_at: str = "2026-01-01T00:00:00Z",
    answer_body: str | None = None,
) -> dict[str, Any]:
    node: dict[str, Any] = {
        "number": number,
        "url": f"https://github.com/owner/repo/discussions/{number}",
        "title": title,
        "body": body,
        "category": {"name": category},
        "answerChosenAt": answer_chosen_at,
        "upvoteCount": upvote_count,
        "reactions": {"totalCount": reaction_count},
        "comments": {"totalCount": comment_count},
        "updatedAt": updated_at,
    }
    if answer_body is not None:
        node["answer"] = {"body": answer_body}
    return node


def _graphql_payload(
    nodes: list[dict[str, Any]], *, has_next_page: bool = False, end_cursor: str | None = None
) -> dict[str, Any]:
    return {
        "data": {
            "repository": {
                "discussions": {
                    "nodes": nodes,
                    "pageInfo": {
                        "hasNextPage": has_next_page,
                        "endCursor": end_cursor,
                    },
                }
            }
        }
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
# Test: Q&A + accepted answer qualifies regardless of engagement counts
# ---------------------------------------------------------------------------


def test_qa_with_accepted_answer_qualifies_regardless_of_engagement() -> None:
    fetcher = GithubDiscussionsFetcher(token="tok")
    nodes = [
        _discussion_node(
            number=1,
            category="Q&A",
            answer_chosen_at="2026-01-02T00:00:00Z",
            upvote_count=0,
            reaction_count=0,
            comment_count=0,
            answer_body="The accepted answer.",
        )
    ]
    with patch("urllib.request.urlopen", return_value=_mock_response(_graphql_payload(nodes))):
        result = fetcher.fetch_qualifying_discussions(_CANONICAL_URL)
    assert len(result) == 1
    assert isinstance(result[0], Discussion)
    assert result[0].is_answered is True
    assert result[0].answer_body == "The accepted answer."


# ---------------------------------------------------------------------------
# Test: non-Q&A qualifies via upvote+reaction engagement threshold
# ---------------------------------------------------------------------------


def test_non_qa_qualifies_via_upvote_and_reaction_threshold() -> None:
    fetcher = GithubDiscussionsFetcher(token="tok")
    nodes = [
        _discussion_node(
            number=2,
            category="General",
            answer_chosen_at=None,
            upvote_count=3,
            reaction_count=2,
            comment_count=0,
        )
    ]
    with patch("urllib.request.urlopen", return_value=_mock_response(_graphql_payload(nodes))):
        result = fetcher.fetch_qualifying_discussions(_CANONICAL_URL)
    assert len(result) == 1
    assert result[0].id == "2"


# ---------------------------------------------------------------------------
# Test: non-Q&A qualifies via reply-count threshold
# ---------------------------------------------------------------------------


def test_non_qa_qualifies_via_reply_count_threshold() -> None:
    fetcher = GithubDiscussionsFetcher(token="tok")
    nodes = [
        _discussion_node(
            number=3,
            category="General",
            answer_chosen_at=None,
            upvote_count=1,
            reaction_count=0,
            comment_count=3,
        )
    ]
    with patch("urllib.request.urlopen", return_value=_mock_response(_graphql_payload(nodes))):
        result = fetcher.fetch_qualifying_discussions(_CANONICAL_URL)
    assert len(result) == 1
    assert result[0].id == "3"


# ---------------------------------------------------------------------------
# Test: low-engagement chatter is skipped
# ---------------------------------------------------------------------------


def test_low_engagement_chatter_is_skipped() -> None:
    fetcher = GithubDiscussionsFetcher(token="tok")
    nodes = [
        _discussion_node(
            number=4,
            category="General",
            answer_chosen_at=None,
            upvote_count=1,
            reaction_count=1,
            comment_count=1,
        )
    ]
    with patch("urllib.request.urlopen", return_value=_mock_response(_graphql_payload(nodes))):
        result = fetcher.fetch_qualifying_discussions(_CANONICAL_URL)
    assert result == []


# ---------------------------------------------------------------------------
# Test: token absent -> no HTTP call, returns []
# ---------------------------------------------------------------------------


def test_no_token_returns_empty_without_api_call() -> None:
    fetcher = GithubDiscussionsFetcher(token=None)
    with patch("urllib.request.urlopen") as mock_open:
        result = fetcher.fetch_qualifying_discussions(_CANONICAL_URL)
    assert result == []
    mock_open.assert_not_called()


# ---------------------------------------------------------------------------
# Test: non-GitHub URL -> no HTTP call, returns []
# ---------------------------------------------------------------------------


def test_non_github_url_returns_empty_without_api_call() -> None:
    fetcher = GithubDiscussionsFetcher(token="tok")
    with patch("urllib.request.urlopen") as mock_open:
        result = fetcher.fetch_qualifying_discussions("https://gitlab.com/owner/repo")
    assert result == []
    mock_open.assert_not_called()


# ---------------------------------------------------------------------------
# Test: GraphQL HTTP error -> returns [] (no raise)
# ---------------------------------------------------------------------------


def test_graphql_http_error_returns_empty() -> None:
    fetcher = GithubDiscussionsFetcher(token="tok")
    with patch("urllib.request.urlopen", side_effect=_mock_http_error(500)):
        result = fetcher.fetch_qualifying_discussions(_CANONICAL_URL)
    assert result == []


# ---------------------------------------------------------------------------
# Test: rate limit (403/429) -> returns [] (no raise)
# ---------------------------------------------------------------------------


def test_graphql_rate_limit_returns_empty() -> None:
    fetcher = GithubDiscussionsFetcher(token="tok")
    with patch("urllib.request.urlopen", side_effect=_mock_http_error(429)):
        result = fetcher.fetch_qualifying_discussions(_CANONICAL_URL)
    assert result == []


# ---------------------------------------------------------------------------
# Test: network error / timeout -> returns [] (no raise)
# ---------------------------------------------------------------------------


def test_graphql_network_error_returns_empty() -> None:
    fetcher = GithubDiscussionsFetcher(token="tok")
    with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
        result = fetcher.fetch_qualifying_discussions(_CANONICAL_URL)
    assert result == []


# ---------------------------------------------------------------------------
# Test: malformed GraphQL payload (missing keys) -> returns [] (no raise)
# ---------------------------------------------------------------------------


def test_malformed_payload_missing_keys_returns_empty() -> None:
    fetcher = GithubDiscussionsFetcher(token="tok")
    with patch("urllib.request.urlopen", return_value=_mock_response({"data": {}})):
        result = fetcher.fetch_qualifying_discussions(_CANONICAL_URL)
    assert result == []


# ---------------------------------------------------------------------------
# Test: malformed GraphQL payload (non-dict) -> returns [] (no raise)
# ---------------------------------------------------------------------------


def test_malformed_payload_non_dict_returns_empty() -> None:
    fetcher = GithubDiscussionsFetcher(token="tok")
    with patch("urllib.request.urlopen", return_value=_mock_response([1, 2, 3])):
        result = fetcher.fetch_qualifying_discussions(_CANONICAL_URL)
    assert result == []


# ---------------------------------------------------------------------------
# Test: malformed JSON body -> returns [] (no raise)
# ---------------------------------------------------------------------------


def test_malformed_json_body_returns_empty() -> None:
    fetcher = GithubDiscussionsFetcher(token="tok")
    resp = MagicMock()
    resp.read.return_value = b"not json{{{"
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=resp):
        result = fetcher.fetch_qualifying_discussions(_CANONICAL_URL)
    assert result == []


# ---------------------------------------------------------------------------
# Test: pagination stops at the hard page cap
# ---------------------------------------------------------------------------


def test_pagination_stops_at_hard_page_cap() -> None:
    fetcher = GithubDiscussionsFetcher(token="tok")
    call_count = [0]

    def _side_effect(req: object, timeout: int = 10) -> MagicMock:
        call_count[0] += 1
        # Always return exactly one qualifying discussion and hasNextPage True,
        # so the only thing that can stop pagination is the hard page cap.
        node = _discussion_node(
            number=call_count[0],
            category="General",
            upvote_count=10,
            reaction_count=10,
        )
        return _mock_response(
            _graphql_payload([node], has_next_page=True, end_cursor=f"cursor-{call_count[0]}")
        )

    with patch("urllib.request.urlopen", side_effect=_side_effect):
        fetcher.fetch_qualifying_discussions(_CANONICAL_URL)

    assert call_count[0] == 10


# ---------------------------------------------------------------------------
# Test: more than 20 qualifying discussions are ranked and truncated to 20
# ---------------------------------------------------------------------------


def test_more_than_20_qualifying_discussions_ranked_and_capped_at_20() -> None:
    fetcher = GithubDiscussionsFetcher(token="tok")
    # 35 qualifying discussions with distinct composite scores (upvote+reaction+comment).
    # Score for discussion number n = n (ensures a clean, unique ranking).
    nodes = [
        _discussion_node(
            number=n,
            category="General",
            upvote_count=n,
            reaction_count=0,
            comment_count=0,
        )
        for n in range(1, 36)
    ]
    with patch("urllib.request.urlopen", return_value=_mock_response(_graphql_payload(nodes))):
        result = fetcher.fetch_qualifying_discussions(_CANONICAL_URL)

    assert len(result) == 20
    # Highest-scored discussions are numbers 35 down to 16.
    expected_ids = {str(n) for n in range(16, 36)}
    assert {d.id for d in result} == expected_ids
    # Ranked descending by composite score.
    scores = [d.upvote_count + d.reaction_count + d.comment_count for d in result]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Test: returned objects are Discussion instances carrying mapped raw fields
# ---------------------------------------------------------------------------


def test_returned_discussion_carries_mapped_raw_fields() -> None:
    fetcher = GithubDiscussionsFetcher(token="tok")
    nodes = [
        _discussion_node(
            number=7,
            title="My title",
            body="My body",
            category="General",
            upvote_count=5,
            reaction_count=0,
            comment_count=0,
            updated_at="2026-03-01T00:00:00Z",
        )
    ]
    with patch("urllib.request.urlopen", return_value=_mock_response(_graphql_payload(nodes))):
        result = fetcher.fetch_qualifying_discussions(_CANONICAL_URL)

    assert len(result) == 1
    d = result[0]
    assert d.id == "7"
    assert d.url == "https://github.com/owner/repo/discussions/7"
    assert d.title == "My title"
    assert d.body == "My body"
    assert d.category == "General"
    assert d.is_answered is False
    assert d.answer_body is None
    assert d.upvote_count == 5
    assert d.reaction_count == 0
    assert d.comment_count == 0
    assert d.updated_at == "2026-03-01T00:00:00Z"
