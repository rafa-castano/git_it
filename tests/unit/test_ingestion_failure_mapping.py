import pytest

from git_it.repository_ingestion.failure_mapping import failure_for_error_code


@pytest.mark.parametrize(
    ("error_code", "expected_status", "expected_stage", "expected_retryable"),
    [
        ("INVALID_URL", "FAILED_VALIDATION", "VALIDATING_URL", False),
        ("UNSUPPORTED_URL", "FAILED_VALIDATION", "VALIDATING_URL", False),
        ("REPOSITORY_NOT_FOUND", "FAILED_FETCH", "FETCHING_METADATA", False),
        (
            "REPOSITORY_PRIVATE_OR_INACCESSIBLE",
            "FAILED_FETCH",
            "FETCHING_METADATA",
            False,
        ),
        ("METADATA_UNAVAILABLE", "FAILED_FETCH", "FETCHING_METADATA", True),
        ("CLONE_TIMEOUT", "FAILED_FETCH", "CLONING_OR_FETCHING", True),
        ("GIT_FETCH_FAILED", "FAILED_FETCH", "CLONING_OR_FETCHING", True),
        ("EXTRACTION_FAILED", "FAILED_EXTRACTION", "EXTRACTING_COMMITS", False),
        ("STORAGE_FAILED", "FAILED_PERSISTENCE", "PERSISTING_FACTS", True),
    ],
)
def test_maps_error_codes_to_terminal_failure_contract(
    error_code: str,
    expected_status: str,
    expected_stage: str,
    expected_retryable: bool,
) -> None:
    failure = failure_for_error_code(error_code)

    assert failure.status == expected_status
    assert failure.error_code == error_code
    assert failure.stage == expected_stage
    assert failure.retryable is expected_retryable


@pytest.mark.parametrize(
    ("error_code", "detected_stage", "expected_status", "expected_retryable"),
    [
        ("LIMIT_EXCEEDED", "EXTRACTING_COMMITS", "LIMIT_EXCEEDED", False),
        ("INGESTION_TIMEOUT", "CLONING_OR_FETCHING", "LIMIT_EXCEEDED", True),
        ("CANCELLED_BY_USER", "PERSISTING_FACTS", "CANCELLED", False),
    ],
)
def test_preserves_dynamic_stage_for_limit_timeout_and_cancellation_failures(
    error_code: str,
    detected_stage: str,
    expected_status: str,
    expected_retryable: bool,
) -> None:
    failure = failure_for_error_code(error_code, stage=detected_stage)

    assert failure.status == expected_status
    assert failure.error_code == error_code
    assert failure.stage == detected_stage
    assert failure.retryable is expected_retryable
