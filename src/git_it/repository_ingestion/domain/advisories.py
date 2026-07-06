"""Domain concepts for GitHub Security Advisories ingestion and narrative evidence
(spec 026).

``SecurityAdvisory`` is the raw, ephemeral fetched candidate — it exists only in
memory as LLM input for summarization and is never persisted or serialized.
There is no code path that writes a ``SecurityAdvisory``'s ``description`` (raw,
community/maintainer-authored text) to any store or API response — mirrors
``Discussion``'s "raw text never rendered" guarantee (spec 022, Security
considerations), applied here to advisory descriptions.

``AdvisoryEvidence`` is the schema-validated, persisted, narrative-facing LLM
output — it mirrors ``DiscussionEvidence``'s structured-output shape
(``domain/discussions.py``). Its ``advisory_url`` validator is the
deterministic, unit-testable form of CODEX.md's evidence-link requirement: an
advisory-sourced claim without a well-formed link back to the specific GitHub
security advisory is rejected at construction time, before it can ever reach
storage or the narrative prompt. ``severity`` is validated against GitHub's
known enum rather than trusted as arbitrary LLM output, closing a path where a
prompt-injected advisory description could otherwise inflate/deflate the
reported severity.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Mirrors _parse_owner_repo's owner/repo charset (infrastructure/github.py): both
# segments exclude "/" so the regex cannot be tricked into matching across path
# boundaries. The GHSA id is lowercase alphanumeric with hyphens (e.g.
# "GHSA-pmv8-rq9r-6j72").
_ADVISORY_URL_RE = re.compile(
    r"^https://github\.com/[^/]+/[^/]+/security/advisories/GHSA-[0-9a-z-]+$"
)


@dataclass(frozen=True)
class SecurityAdvisory:
    """A raw, fetched GitHub security advisory candidate. Never persisted or serialized."""

    ghsa_id: str
    cve_id: str | None
    summary: str
    description: str
    severity: str
    html_url: str
    published_at: str | None


class AdvisoryEvidence(BaseModel):
    """Schema-validated, persisted LLM summary of a single qualifying advisory."""

    ghsa_id: str
    advisory_url: str
    severity: Literal["low", "medium", "high", "critical"]
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    limitations: list[str] = Field(default_factory=list)
    source_inputs: list[str]
    generated_at: datetime
    model: str

    @field_validator("advisory_url")
    @classmethod
    def _validate_advisory_url(cls, value: str) -> str:
        if not value or not _ADVISORY_URL_RE.match(value):
            raise ValueError(
                "advisory_url must match "
                "https://github.com/{owner}/{repo}/security/advisories/GHSA-{id}"
            )
        return value
