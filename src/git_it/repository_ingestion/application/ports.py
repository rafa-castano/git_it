from typing import Protocol


class GitGatewayError(Exception):
    safe_message = "Repository fetch failed safely before analysis could start."

    def __init__(self, *, error_code: str) -> None:
        super().__init__(self.safe_message)
        self.error_code = error_code


class GitGateway(Protocol):
    def clone_or_fetch(self, canonical_url: str) -> None: ...
