import pytest

from git_it.repository_ingestion.domain.url_contract import (
    RepositoryUrlValidationError,
    parse_repository_url,
)


def assert_repository_url_validation_error(
    error: RepositoryUrlValidationError,
    *,
    error_code: str,
) -> None:
    assert error.error_code == error_code
    assert error.stage == "VALIDATING_URL"
    assert error.retryable is False


def test_accepts_canonical_github_https_repository_url() -> None:
    parsed = parse_repository_url("https://github.com/owner/repo")

    assert parsed.owner == "owner"
    assert parsed.repo == "repo"
    assert parsed.canonical_url == "https://github.com/owner/repo"


def test_normalizes_github_https_repository_url_with_git_suffix() -> None:
    parsed = parse_repository_url("https://github.com/owner/repo.git")

    assert parsed.owner == "owner"
    assert parsed.repo == "repo"
    assert parsed.canonical_url == "https://github.com/owner/repo"


def test_rejects_unsupported_repository_host_before_git_tooling() -> None:
    with pytest.raises(RepositoryUrlValidationError) as error:
        parse_repository_url("https://gitlab.com/owner/repo")

    assert_repository_url_validation_error(error.value, error_code="UNSUPPORTED_URL")


def test_rejects_unsupported_repository_scheme_before_git_tooling() -> None:
    with pytest.raises(RepositoryUrlValidationError) as error:
        parse_repository_url("http://github.com/owner/repo")

    assert_repository_url_validation_error(error.value, error_code="UNSUPPORTED_URL")


def test_rejects_github_owner_url_without_repository_name() -> None:
    with pytest.raises(RepositoryUrlValidationError) as error:
        parse_repository_url("https://github.com/owner")

    assert_repository_url_validation_error(error.value, error_code="INVALID_URL")


def test_rejects_github_tree_subpath_before_git_tooling() -> None:
    with pytest.raises(RepositoryUrlValidationError) as error:
        parse_repository_url("https://github.com/owner/repo/tree/main")

    assert_repository_url_validation_error(error.value, error_code="INVALID_URL")


def test_rejects_github_pull_request_subpath_before_git_tooling() -> None:
    with pytest.raises(RepositoryUrlValidationError) as error:
        parse_repository_url("https://github.com/owner/repo/pull/123")

    assert_repository_url_validation_error(error.value, error_code="INVALID_URL")


def test_rejects_malformed_repository_url_before_git_tooling() -> None:
    with pytest.raises(RepositoryUrlValidationError) as error:
        parse_repository_url("not-a-url")

    assert_repository_url_validation_error(error.value, error_code="INVALID_URL")


def test_validation_errors_include_safe_user_facing_message() -> None:
    with pytest.raises(RepositoryUrlValidationError) as error:
        parse_repository_url("not-a-url")

    assert (
        error.value.safe_message == "Repository URL must be a public GitHub HTTPS repository URL."
    )
    assert "not-a-url" not in error.value.safe_message


def test_rejects_credential_bearing_url_without_leaking_credentials() -> None:
    with pytest.raises(RepositoryUrlValidationError) as error:
        parse_repository_url("https://token@github.com/owner/repo")

    assert_repository_url_validation_error(error.value, error_code="UNSUPPORTED_URL")
    assert "token" not in error.value.safe_message


def test_rejects_git_suffix_that_would_leave_empty_repository_name() -> None:
    with pytest.raises(RepositoryUrlValidationError) as error:
        parse_repository_url("https://github.com/owner/.git")

    assert_repository_url_validation_error(error.value, error_code="INVALID_URL")
