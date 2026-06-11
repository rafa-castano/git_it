from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class ParsedRepositoryUrl:
    owner: str
    repo: str
    canonical_url: str


class RepositoryUrlValidationError(ValueError):
    def __init__(self, error_code: str, stage: str, retryable: bool) -> None:
        self.error_code = error_code
        self.stage = stage
        self.retryable = retryable
        self.safe_message = "Repository URL must be a public GitHub HTTPS repository URL."
        super().__init__(error_code)


def parse_repository_url(raw_url: str) -> ParsedRepositoryUrl:
    parsed = urlparse(raw_url)
    if not parsed.scheme or not parsed.netloc:
        raise RepositoryUrlValidationError(
            error_code="INVALID_URL",
            stage="VALIDATING_URL",
            retryable=False,
        )
    if parsed.scheme != "https" or parsed.netloc != "github.com":
        raise RepositoryUrlValidationError(
            error_code="UNSUPPORTED_URL",
            stage="VALIDATING_URL",
            retryable=False,
        )
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) != 2:
        raise RepositoryUrlValidationError(
            error_code="INVALID_URL",
            stage="VALIDATING_URL",
            retryable=False,
        )
    owner, repo = path_parts[0], path_parts[1]
    if repo.endswith(".git"):
        repo = repo.removesuffix(".git")
    if not owner or not repo:
        raise RepositoryUrlValidationError(
            error_code="INVALID_URL",
            stage="VALIDATING_URL",
            retryable=False,
        )

    return ParsedRepositoryUrl(
        owner=owner,
        repo=repo,
        canonical_url=f"https://github.com/{owner}/{repo}",
    )
