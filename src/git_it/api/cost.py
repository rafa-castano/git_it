"""Cost model constants for the analysis estimate endpoint.

All pricing lives here. Update these values when LLM provider pricing changes;
routes/repos.py imports from this module so the endpoint reflects the update
automatically.
"""

# claude-haiku-4-5 approximate cost per commit analysis LLM call
LLM_COST_PER_CALL_USD = 0.0008

# claude-sonnet-4-6 narrative (case study) cost model
SONNET_INPUT_COST_PER_TOKEN = 3.0 / 1_000_000  # $3 / MTok
SONNET_OUTPUT_COST_PER_TOKEN = 15.0 / 1_000_000  # $15 / MTok
NARRATIVE_BASE_INPUT_TOKENS = 500  # system prompt overhead
NARRATIVE_TOKENS_PER_COMMIT = 45  # per-commit contribution to the user message
NARRATIVE_OUTPUT_TOKENS = 4000  # conservative average output token count


def estimate_narrative_cost(total_commits: int) -> float:
    """Return the estimated case-study narrative cost in USD.

    Returns 0.0 when there are no commits (nothing to narrate).
    The result is rounded to 4 decimal places, matching the precision used in
    the AnalyzeEstimateResponse schema.
    """
    if total_commits == 0:
        return 0.0
    input_tokens = NARRATIVE_BASE_INPUT_TOKENS + total_commits * NARRATIVE_TOKENS_PER_COMMIT
    return round(
        input_tokens * SONNET_INPUT_COST_PER_TOKEN
        + NARRATIVE_OUTPUT_TOKENS * SONNET_OUTPUT_COST_PER_TOKEN,
        4,
    )
