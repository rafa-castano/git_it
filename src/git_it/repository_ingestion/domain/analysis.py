import enum

from pydantic import BaseModel, Field


class CommitCategory(enum.StrEnum):
    FEATURE = "feature"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    TEST = "test"
    DOCS = "docs"
    BUILD = "build"
    SECURITY = "security"
    PERFORMANCE = "performance"
    CHORE = "chore"
    UNKNOWN = "unknown"


class RiskLevel(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class EvidenceRef(BaseModel):
    commit_sha: str
    file_path: str | None = None
    quote: str | None = None


class CommitAnalysis(BaseModel):
    commit_sha: str
    summary: str
    summary_beginner: str | None = None
    summary_expert: str | None = None
    category: CommitCategory
    intent: str | None = None
    intent_is_inferred: bool = False
    affected_components: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
