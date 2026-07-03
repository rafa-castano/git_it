from dataclasses import dataclass, field


@dataclass(frozen=True)
class LanguageBreakdown:
    language: str
    bytes: int


@dataclass(frozen=True)
class RepoMetadata:
    stars: int
    languages: tuple[LanguageBreakdown, ...] = field(default_factory=tuple)
