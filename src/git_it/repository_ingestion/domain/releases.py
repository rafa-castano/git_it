"""Domain concepts for GitHub Releases ingestion and narrative evidence (spec 026).

``Release`` is the raw, ephemeral fetched candidate — it exists only in memory as
LLM input for summarization and is never persisted or serialized. There is no
code path that writes a ``Release``'s ``body`` (raw release-notes markdown) to
any store or API response — mirrors ``Discussion``'s "raw text never rendered"
guarantee (spec 022, Security considerations), applied here to release notes.

``ReleaseEvidence`` is the schema-validated, persisted, narrative-facing LLM
output — it mirrors ``DiscussionEvidence``'s structured-output shape
(``domain/discussions.py``). Its ``release_url`` validator is the deterministic,
unit-testable form of CODEX.md's evidence-link requirement: a release-sourced
claim without a well-formed link back to the specific GitHub release is rejected
at construction time, before it can ever reach storage or the narrative prompt.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Mirrors _parse_owner_repo's owner/repo charset (infrastructure/github.py): both
# segments exclude "/" so the regex cannot be tricked into matching across path
# boundaries. The tag segment is non-empty and excludes whitespace — tags
# legitimately contain dots (e.g. "v1.2.3") and GitHub percent-encodes any "/"
# a tag name might contain, so "\S+" is correct and not over-restrictive.
_RELEASE_URL_RE = re.compile(r"^https://github\.com/[^/]+/[^/]+/releases/tag/\S+$")


@dataclass(frozen=True)
class Release:
    """A raw, fetched GitHub release candidate. Never persisted or serialized."""

    tag_name: str
    name: str | None
    body: str | None
    html_url: str
    published_at: str | None
    prerelease: bool


class ReleaseEvidence(BaseModel):
    """Schema-validated, persisted LLM summary of a single qualifying release."""

    tag_name: str
    release_url: str
    claim_type: Literal["breaking_change", "feature_release", "bugfix_release", "security_release"]
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    limitations: list[str] = Field(default_factory=list)
    source_inputs: list[str]
    generated_at: datetime
    model: str

    @field_validator("release_url")
    @classmethod
    def _validate_release_url(cls, value: str) -> str:
        if not value or not _RELEASE_URL_RE.match(value):
            raise ValueError(
                "release_url must match https://github.com/{owner}/{repo}/releases/tag/{tag}"
            )
        return value
