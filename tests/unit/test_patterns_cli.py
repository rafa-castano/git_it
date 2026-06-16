from pathlib import Path

import pytest

from git_it.repository_ingestion.domain.patterns import Hotspot, PatternReport
from git_it.repository_ingestion.interfaces.cli import main


def _hotspot(file_path: str = "src/main.py", commit_count: int = 10) -> Hotspot:
    return Hotspot(
        file_path=file_path,
        commit_count=commit_count,
        total_insertions=50,
        total_deletions=20,
    )


class FakePatternService:
    def __init__(self, report: PatternReport | None = None) -> None:
        self._report = report or PatternReport(repository_id="", hotspots=[])
        self.calls: list[tuple[str, int]] = []

    def detect(self, repository_id: str, *, hotspot_threshold: int = 5) -> PatternReport:
        self.calls.append((repository_id, hotspot_threshold))
        return self._report


def _factory(service: FakePatternService):  # type: ignore[no-untyped-def]
    def factory(*, project_root: Path, repository_id: str) -> FakePatternService:
        return service

    return factory


def test_patterns_exits_zero(tmp_path: Path) -> None:
    code = main(
        ["patterns", "https://github.com/owner/repo"],
        project_root=tmp_path,
        pattern_factory=_factory(FakePatternService()),
    )
    assert code == 0


def test_patterns_shows_no_data_message_when_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(
        ["patterns", "https://github.com/owner/repo"],
        project_root=tmp_path,
        pattern_factory=_factory(FakePatternService()),
    )
    captured = capsys.readouterr()
    assert "No" in captured.out


def test_patterns_displays_hotspot_file_and_commit_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = PatternReport(repository_id="repo-1", hotspots=[_hotspot("src/auth.py", 15)])
    main(
        ["patterns", "https://github.com/owner/repo"],
        project_root=tmp_path,
        pattern_factory=_factory(FakePatternService(report=report)),
    )
    captured = capsys.readouterr()
    assert "src/auth.py" in captured.out
    assert "15" in captured.out


def test_patterns_passes_threshold_to_service(tmp_path: Path) -> None:
    service = FakePatternService()
    main(
        ["patterns", "https://github.com/owner/repo", "--hotspot-threshold", "3"],
        project_root=tmp_path,
        pattern_factory=_factory(service),
    )
    assert service.calls[0][1] == 3
