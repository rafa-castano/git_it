import pytest

from git_it.repository_ingestion.application_service import (
    GitGatewayError,
    RepositoryIngestionService,
)


class SpyGitGateway:
    def __init__(self) -> None:
        self.clone_or_fetch_calls: list[str] = []

    def clone_or_fetch(self, canonical_url: str) -> None:
        self.clone_or_fetch_calls.append(canonical_url)


class FailingGitGateway:
    def __init__(self, *, error_code: str) -> None:
        self.error_code = error_code
        self.clone_or_fetch_calls: list[str] = []

    def clone_or_fetch(self, canonical_url: str) -> None:
        self.clone_or_fetch_calls.append(canonical_url)
        raise GitGatewayError(error_code=self.error_code)


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


@pytest.mark.parametrize(
    "raw_url",
    [
        "https://github.com/owner/repo",
        "https://github.com/owner/repo.git",
    ],
)
def test_ingestion_service_starts_clone_or_fetch_with_canonical_url(raw_url: str) -> None:
    git_gateway = SpyGitGateway()
    service = RepositoryIngestionService(git_gateway=git_gateway)

    result = service.ingest(raw_url)

    assert result.status == "CLONING_OR_FETCHING"
    assert result.error_code is None
    assert result.stage == "CLONING_OR_FETCHING"
    assert result.retryable is False
    assert result.safe_message is None
    assert git_gateway.clone_or_fetch_calls == ["https://github.com/owner/repo"]


@pytest.mark.parametrize(
    ("error_code", "expected_stage", "expected_retryable"),
    [
        ("REPOSITORY_NOT_FOUND", "FETCHING_METADATA", False),
        ("CLONE_TIMEOUT", "CLONING_OR_FETCHING", True),
    ],
)
def test_ingestion_service_maps_git_gateway_failures_to_safe_failure_result(
    error_code: str,
    expected_stage: str,
    expected_retryable: bool,
) -> None:
    git_gateway = FailingGitGateway(error_code=error_code)
    service = RepositoryIngestionService(git_gateway=git_gateway)

    result = service.ingest("https://github.com/owner/repo")

    assert result.status == "FAILED_FETCH"
    assert result.error_code == error_code
    assert result.stage == expected_stage
    assert result.retryable is expected_retryable
    assert result.safe_message == "Repository fetch failed safely before analysis could start."
    assert git_gateway.clone_or_fetch_calls == ["https://github.com/owner/repo"]
