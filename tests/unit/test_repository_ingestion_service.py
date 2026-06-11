import pytest

from git_it.repository_ingestion.application_service import RepositoryIngestionService


class SpyGitGateway:
    def __init__(self) -> None:
        self.clone_or_fetch_calls: list[str] = []

    def clone_or_fetch(self, canonical_url: str) -> None:
        self.clone_or_fetch_calls.append(canonical_url)


@pytest.mark.parametrize(
    ("raw_url", "expected_error_code"),
    [
        ("not-a-url", "INVALID_URL"),
        ("https://gitlab.com/owner/repo", "UNSUPPORTED_URL"),
    ],
)
def test_ingestion_service_returns_validation_failure_without_git_tooling(
    raw_url: str,
    expected_error_code: str,
) -> None:
    git_gateway = SpyGitGateway()
    service = RepositoryIngestionService(git_gateway=git_gateway)

    result = service.ingest(raw_url)

    assert result.status == "FAILED_VALIDATION"
    assert result.error_code == expected_error_code
    assert result.stage == "VALIDATING_URL"
    assert result.retryable is False
    assert result.safe_message == "Repository URL must be a public GitHub HTTPS repository URL."
    assert git_gateway.clone_or_fetch_calls == []
