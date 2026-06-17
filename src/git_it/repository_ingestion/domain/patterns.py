from dataclasses import dataclass, field


@dataclass(frozen=True)
class PatternExplanation:
    pattern_type: str  # "hotspot", "bugfix_recurrence", "refactor_wave", etc.
    pattern_key: str  # file_path for hotspot/ownership, component for bugfix, else ""
    why_it_matters: str  # 1-2 sentences: educational significance
    engineer_takeaway: str  # 1 actionable lesson
    confidence_note: str = ""  # brief note on evidence quality (can be empty)


@dataclass(frozen=True)
class Hotspot:
    file_path: str
    commit_count: int
    total_insertions: int
    total_deletions: int
    evidence_commit_shas: tuple[str, ...] = ()
    time_range: tuple[str, str] | None = None
    confidence: float = 0.0

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
    evidence_commit_shas: tuple[str, ...] = ()
    time_range: tuple[str, str] | None = None
    confidence: float = 0.0


@dataclass(frozen=True)
class RefactorWave:
    commit_count: int
    refactor_ratio: float
    evidence_commit_shas: tuple[str, ...] = ()
    time_range: tuple[str, str] | None = None
    confidence: float = 0.0


@dataclass(frozen=True)
class TestGrowthSignal:
    test_commit_count: int
    bugfix_commit_count: int
    test_to_bugfix_ratio: float
    evidence_commit_shas: tuple[str, ...] = ()
    time_range: tuple[str, str] | None = None
    confidence: float = 0.0


@dataclass(frozen=True)
class RevertSignal:
    revert_count: int
    revert_ratio: float
    evidence_commit_shas: tuple[str, ...] = ()
    time_range: tuple[str, str] | None = None
    confidence: float = 0.0


@dataclass(frozen=True)
class OwnershipConcentration:
    file_path: str
    author_count: int
    commit_count: int
    evidence_commit_shas: tuple[str, ...] = ()
    time_range: tuple[str, str] | None = None
    confidence: float = 0.0


@dataclass
class PatternReport:
    repository_id: str
    hotspots: list[Hotspot]
    category_counts: list[CategoryCount] = field(default_factory=list)
    bugfix_recurrences: list[BugfixRecurrence] = field(default_factory=list)
    refactor_wave: RefactorWave | None = None
    revert_signal: RevertSignal | None = None
    test_growth_signal: TestGrowthSignal | None = None
    ownership_concentrations: list[OwnershipConcentration] = field(default_factory=list)
    explanations: list[PatternExplanation] = field(default_factory=list)  # LLM synthesis
