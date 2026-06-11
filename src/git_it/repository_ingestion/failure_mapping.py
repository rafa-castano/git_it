from dataclasses import dataclass


@dataclass(frozen=True)
class IngestionFailure:
    status: str
    error_code: str
    stage: str
    retryable: bool


_STATIC_FAILURES: dict[str, IngestionFailure] = {
    "INVALID_URL": IngestionFailure(
        status="FAILED_VALIDATION",
        error_code="INVALID_URL",
        stage="VALIDATING_URL",
        retryable=False,
    ),
    "UNSUPPORTED_URL": IngestionFailure(
        status="FAILED_VALIDATION",
        error_code="UNSUPPORTED_URL",
        stage="VALIDATING_URL",
        retryable=False,
    ),
    "REPOSITORY_NOT_FOUND": IngestionFailure(
        status="FAILED_FETCH",
        error_code="REPOSITORY_NOT_FOUND",
        stage="FETCHING_METADATA",
        retryable=False,
    ),
    "REPOSITORY_PRIVATE_OR_INACCESSIBLE": IngestionFailure(
        status="FAILED_FETCH",
        error_code="REPOSITORY_PRIVATE_OR_INACCESSIBLE",
        stage="FETCHING_METADATA",
        retryable=False,
    ),
    "METADATA_UNAVAILABLE": IngestionFailure(
        status="FAILED_FETCH",
        error_code="METADATA_UNAVAILABLE",
        stage="FETCHING_METADATA",
        retryable=True,
    ),
    "CLONE_TIMEOUT": IngestionFailure(
        status="FAILED_FETCH",
        error_code="CLONE_TIMEOUT",
        stage="CLONING_OR_FETCHING",
        retryable=True,
    ),
    "GIT_FETCH_FAILED": IngestionFailure(
        status="FAILED_FETCH",
        error_code="GIT_FETCH_FAILED",
        stage="CLONING_OR_FETCHING",
        retryable=True,
    ),
    "EXTRACTION_FAILED": IngestionFailure(
        status="FAILED_EXTRACTION",
        error_code="EXTRACTION_FAILED",
        stage="EXTRACTING_COMMITS",
        retryable=False,
    ),
    "STORAGE_FAILED": IngestionFailure(
        status="FAILED_PERSISTENCE",
        error_code="STORAGE_FAILED",
        stage="PERSISTING_FACTS",
        retryable=True,
    ),
}

_DYNAMIC_FAILURES: dict[str, tuple[str, bool]] = {
    "LIMIT_EXCEEDED": ("LIMIT_EXCEEDED", False),
    "INGESTION_TIMEOUT": ("LIMIT_EXCEEDED", True),
    "CANCELLED_BY_USER": ("CANCELLED", False),
}


def failure_for_error_code(error_code: str, *, stage: str | None = None) -> IngestionFailure:
    if error_code in _STATIC_FAILURES:
        return _STATIC_FAILURES[error_code]

    if error_code in _DYNAMIC_FAILURES:
        if stage is None:
            raise ValueError(f"stage is required for {error_code}")
        status, retryable = _DYNAMIC_FAILURES[error_code]
        return IngestionFailure(
            status=status,
            error_code=error_code,
            stage=stage,
            retryable=retryable,
        )

    raise KeyError(error_code)
