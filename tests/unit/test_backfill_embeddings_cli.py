from pathlib import Path

import pytest

from git_it.repository_ingestion.application.embedding_backfill_service import (
    EmbeddingBackfillResult,
)
from git_it.repository_ingestion.interfaces.cli import main


class FakeBackfillService:
    def __init__(
        self,
        *,
        estimate: int = 0,
        result: EmbeddingBackfillResult | None = None,
    ) -> None:
        self._estimate = estimate
        self._result = result or EmbeddingBackfillResult(embedded=0, already_present=0, failed=0)
        self.estimate_calls: list[str] = []
        self.backfill_calls: list[str] = []

    def estimate_backfill_calls(self, repository_id: str) -> int:
        self.estimate_calls.append(repository_id)
        return self._estimate

    def backfill(self, repository_id: str) -> EmbeddingBackfillResult:
        self.backfill_calls.append(repository_id)
        return self._result


def _factory(service: FakeBackfillService | None):  # type: ignore[no-untyped-def]
    def factory(*, project_root: Path) -> FakeBackfillService | None:
        return service

    return factory


def test_backfill_embeddings_no_key_prints_message_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """factory returning None (no embedding client) is a clean no-op success."""
    code = main(
        ["backfill-embeddings", "https://github.com/owner/repo"],
        project_root=tmp_path,
        backfill_factory=_factory(None),
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "OPENAI_API_KEY" in captured.out


def test_backfill_embeddings_zero_estimate_prints_nothing_to_backfill(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    service = FakeBackfillService(estimate=0)
    code = main(
        ["backfill-embeddings", "https://github.com/owner/repo"],
        project_root=tmp_path,
        backfill_factory=_factory(service),
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "nothing to backfill" in captured.out.lower()
    assert service.backfill_calls == []


def test_backfill_embeddings_aborts_when_budget_exceeded_and_not_confirmed(
    tmp_path: Path,
) -> None:
    service = FakeBackfillService(estimate=100)

    code = main(
        ["backfill-embeddings", "https://github.com/owner/repo"],
        project_root=tmp_path,
        backfill_factory=_factory(service),
        budget_confirm_fn=lambda n: False,
        budget_threshold=10,
    )

    assert code == 1
    assert service.backfill_calls == []


def test_backfill_embeddings_yes_flag_skips_budget_confirmation(tmp_path: Path) -> None:
    service = FakeBackfillService(estimate=999)
    confirm_called: list[int] = []

    def _confirm(n: int) -> bool:
        confirm_called.append(n)
        return False  # would abort if called

    code = main(
        ["backfill-embeddings", "https://github.com/owner/repo", "--yes"],
        project_root=tmp_path,
        backfill_factory=_factory(service),
        budget_confirm_fn=_confirm,
        budget_threshold=10,
    )

    assert code == 0
    assert confirm_called == []
    assert len(service.backfill_calls) == 1


def test_backfill_embeddings_proceeds_when_budget_confirmed(tmp_path: Path) -> None:
    service = FakeBackfillService(
        estimate=100,
        result=EmbeddingBackfillResult(embedded=100, already_present=0, failed=0),
    )

    code = main(
        ["backfill-embeddings", "https://github.com/owner/repo"],
        project_root=tmp_path,
        backfill_factory=_factory(service),
        budget_confirm_fn=lambda n: True,
        budget_threshold=10,
    )

    assert code == 0
    assert len(service.backfill_calls) == 1


def test_backfill_embeddings_no_confirmation_when_under_threshold(tmp_path: Path) -> None:
    service = FakeBackfillService(estimate=5)
    confirm_called: list[int] = []

    def _confirm(n: int) -> bool:
        confirm_called.append(n)
        return True

    code = main(
        ["backfill-embeddings", "https://github.com/owner/repo"],
        project_root=tmp_path,
        backfill_factory=_factory(service),
        budget_confirm_fn=_confirm,
        budget_threshold=10,
    )

    assert code == 0
    assert confirm_called == []
    assert len(service.backfill_calls) == 1


def test_backfill_embeddings_prints_result_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    service = FakeBackfillService(
        estimate=3,
        result=EmbeddingBackfillResult(embedded=2, already_present=5, failed=1),
    )

    main(
        ["backfill-embeddings", "https://github.com/owner/repo"],
        project_root=tmp_path,
        backfill_factory=_factory(service),
        budget_confirm_fn=lambda n: True,
        budget_threshold=10,
    )

    captured = capsys.readouterr()
    assert "2" in captured.out
    assert "5" in captured.out
    assert "1" in captured.out
