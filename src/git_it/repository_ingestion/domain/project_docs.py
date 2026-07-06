"""Domain concepts for captured project documentation (spec 025).

``ProjectDocContent`` is the persisted, backend-agnostic record of a
repository's root-level README/CHANGELOG excerpt, captured once from the bare
git clone already used for commit mining (no new external API call, no new
credential). Like ``EmbeddedChunk`` in ``domain/embeddings.py``, this is a
plain frozen dataclass — there is no LLM output to validate here, only an
internal persistence shape for raw-truncated repository text this codebase
read itself. One record per repository (not one row per source), since there
are always exactly two possible sources: README and CHANGELOG.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ProjectDocContent:
    """A repository's captured, truncated README/CHANGELOG excerpt."""

    repository_id: str
    readme_text: str | None
    readme_truncated: bool
    changelog_text: str | None
    changelog_truncated: bool
    captured_at: datetime
