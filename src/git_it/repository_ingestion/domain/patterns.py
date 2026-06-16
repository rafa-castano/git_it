from dataclasses import dataclass


@dataclass(frozen=True)
class Hotspot:
    file_path: str
    commit_count: int
    total_insertions: int
    total_deletions: int

    @property
    def churn(self) -> int:
        return self.total_insertions + self.total_deletions


@dataclass
class PatternReport:
    repository_id: str
    hotspots: list[Hotspot]
