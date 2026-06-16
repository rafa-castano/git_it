from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExtractedFileChange:
    path: str
    insertions: int
    deletions: int


@dataclass(frozen=True)
class ExtractedCommit:
    sha: str
    committed_at: str
    message: str
    author_name: str
    committer_name: str
    parent_shas: tuple[str, ...]
    file_changes: tuple[ExtractedFileChange, ...] = field(default_factory=tuple)
