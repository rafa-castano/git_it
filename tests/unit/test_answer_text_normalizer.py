"""Spec 016 — Ask tab answer formatting.

`normalize_answer_text` is a pure, deterministic function that fixes two LLM
answer-formatting defects before the text is displayed: sentences that run
together with no space after sentence-ending punctuation, and excessive blank
lines. It must NOT rewrite decimals, URLs, ellipses, or text inside fenced code
blocks — those are the guard cases this suite exists to lock down.

The frontend (`normalizeAnswerText` in `src/git_it/static/app.js`) mirrors this
exact logic for the Ask tab's live-streaming render path. They must stay in
sync — see the code comments on both sides.
"""

from git_it.chat.service import normalize_answer_text


def test_inserts_space_after_run_on_sentence_period() -> None:
    text = "...backed by evidence.The next commit introduced tests."
    assert normalize_answer_text(text) == (
        "...backed by evidence. The next commit introduced tests."
    )


def test_inserts_space_after_run_on_question_mark() -> None:
    text = "Is this safe?The tests say no."
    assert normalize_answer_text(text) == "Is this safe? The tests say no."


def test_inserts_space_after_run_on_exclamation_mark() -> None:
    text = "Ship it!The pipeline is green."
    assert normalize_answer_text(text) == "Ship it! The pipeline is green."


def test_collapses_three_or_more_blank_lines_to_one() -> None:
    text = "First paragraph.\n\n\n\nSecond paragraph."
    assert normalize_answer_text(text) == "First paragraph.\n\nSecond paragraph."


def test_collapses_many_consecutive_newlines_to_one_blank_line() -> None:
    text = "A\n\n\n\n\n\nB"
    assert normalize_answer_text(text) == "A\n\nB"


def test_does_not_touch_already_correct_text() -> None:
    text = "This is fine. So is this. And this too."
    assert normalize_answer_text(text) == text


# ---------------------------------------------------------------------------
# Guard cases — the whole point of this suite
# ---------------------------------------------------------------------------


def test_does_not_split_decimal_version_numbers() -> None:
    text = "This project targets Python 3.12 and uses uv."
    assert normalize_answer_text(text) == text


def test_does_not_insert_space_inside_a_url() -> None:
    text = "See https://github.com/octocat/Hello-World for the source."
    assert normalize_answer_text(text) == text


def test_does_not_touch_an_ellipsis() -> None:
    text = "The history trails off...Nothing else is known."
    assert normalize_answer_text(text) == text


def test_does_not_split_common_abbreviation() -> None:
    text = "The fix shipped circa Q3 2024 (see e.g. the changelog)."
    assert normalize_answer_text(text) == text


def test_does_not_rewrite_text_inside_a_fenced_code_block() -> None:
    text = (
        "Here is the relevant snippet:\n\n"
        "```python\n"
        "x = 3.12\ndef f():pass\n"
        "```\n\n"
        "That code came from evidence.The commit that added it is abc123."
    )
    result = normalize_answer_text(text)
    assert "def f():pass\n" in result  # code fence untouched
    assert "x = 3.12" in result
    assert "evidence. The commit" in result  # outside the fence, still fixed


def test_empty_string_returns_empty_string() -> None:
    assert normalize_answer_text("") == ""


def test_none_like_falsy_input_does_not_raise() -> None:
    assert normalize_answer_text(None) == ""  # type: ignore[arg-type]
