from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedCommit:
    sha: str
    committed_at: str
    message: str
    author_name: str
    committer_name: str
    parent_shas: tuple[str, ...]
