from dataclasses import dataclass, field


@dataclass(frozen=True)
class Hotspot:
    file_path: str
    commit_count: int
    total_insertions: int
    total_deletions: int

    @property
    def churn(self) -> int:
        return self.total_insertions + self.total_deletions


@dataclass(frozen=True)
class CategoryCount:
    category: str
    count: int


@dataclass(frozen=True)
class BugfixRecurrence:
    component: str
    bugfix_commit_count: int


@dataclass(frozen=True)
class RefactorWave:
    commit_count: int
    refactor_ratio: float


@dataclass(frozen=True)
class TestGrowthSignal:
    test_commit_count: int
    bugfix_commit_count: int
    test_to_bugfix_ratio: float


@dataclass(frozen=True)
class OwnershipConcentration:
    file_path: str
    author_count: int
    commit_count: int


@dataclass
class PatternReport:
    repository_id: str
    hotspots: list[Hotspot]
    category_counts: list[CategoryCount] = field(default_factory=list)
    bugfix_recurrences: list[BugfixRecurrence] = field(default_factory=list)
    refactor_wave: RefactorWave | None = None
    test_growth_signal: TestGrowthSignal | None = None
    ownership_concentrations: list[OwnershipConcentration] = field(default_factory=list)
