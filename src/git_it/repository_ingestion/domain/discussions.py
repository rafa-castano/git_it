"""Domain concepts for GitHub Discussions ingestion and narrative evidence (spec 022).

``Discussion`` is the raw, ephemeral fetched candidate — it exists only in memory as LLM
input for summarization and is never persisted or serialized. There is no code path that
writes a ``Discussion``'s ``title``/``body``/``answer_body`` to any store or API response;
that guarantee is the load-bearing mechanism behind "raw discussion text is never
rendered" (see spec 022, Security considerations).

``DiscussionEvidence`` is the schema-validated, persisted, narrative-facing LLM output —
it mirrors ``CommitAnalysis``'s structured-output shape (``domain/analysis.py``). Its
``discussion_url`` validator is the deterministic, unit-testable form of CODEX.md's
evidence-link requirement: a discussion-sourced claim without a well-formed link back to
the specific GitHub discussion is rejected at construction time, before it can ever reach
storage or the narrative prompt.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Mirrors _parse_owner_repo's owner/repo charset (infrastructure/github.py): both
# segments exclude "/" so the regex cannot be tricked into matching across path
# boundaries. The discussion number must be purely numeric.
_DISCUSSION_URL_RE = re.compile(r"^https://github\.com/[^/]+/[^/]+/discussions/\d+$")


@dataclass(frozen=True)
class Discussion:
    """A raw, fetched GitHub Discussion candidate. Never persisted or serialized."""

    id: str
    url: str
    title: str
    body: str
    answer_body: str | None
    category: str
    is_answered: bool
    upvote_count: int
    reaction_count: int
    comment_count: int
    updated_at: str


class DiscussionEvidence(BaseModel):
    """Schema-validated, persisted LLM summary of a single qualifying discussion."""

    discussion_id: str
    discussion_url: str
    claim_type: Literal["design_rationale", "pain_point"]
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    limitations: list[str] = Field(default_factory=list)
    source_inputs: list[str]
    generated_at: datetime
    model: str

    @field_validator("discussion_url")
    @classmethod
    def _validate_discussion_url(cls, value: str) -> str:
        if not value or not _DISCUSSION_URL_RE.match(value):
            raise ValueError(
                "discussion_url must match https://github.com/{owner}/{repo}/discussions/{number}"
            )
        return value
