from dataclasses import dataclass, field


@dataclass(frozen=True)
class GithubContext:
    pr_number: int | None = None
    pr_title: str | None = None
    pr_body: str | None = None
    issue_numbers: tuple[int, ...] = field(default_factory=tuple)
    issue_bodies: tuple[str, ...] = field(default_factory=tuple)
    has_pr: bool = False
