from git_it.repository_ingestion.application.ports import LLMMessage
from git_it.repository_ingestion.domain.analysis import CommitAnalysis

_DEFAULT_MODEL = "anthropic/claude-haiku-4-5-20251001"
_DEFAULT_MAX_TOKENS = 4096
_ANALYSIS_MAX_TOKENS = 1024


class LiteLLMLLMClient:
    def __init__(self, *, model: str = _DEFAULT_MODEL) -> None:
        self._model = model

    def complete(self, messages: list[LLMMessage]) -> str:
        import litellm

        litellm_messages = [{"role": m.role, "content": m.content} for m in messages]
        response = litellm.completion(
            model=self._model,
            messages=litellm_messages,
            max_tokens=_DEFAULT_MAX_TOKENS,
        )
        content = response.choices[0].message.content  # type: ignore[union-attr]
        return content or ""


class InstructorCommitAnalysisAdapter:
    def __init__(self, *, model: str = _DEFAULT_MODEL) -> None:
        self._model = model

    def analyze_commit(self, messages: list[LLMMessage]) -> CommitAnalysis:
        import instructor
        import litellm

        client = instructor.from_litellm(litellm.completion)
        litellm_messages = [{"role": m.role, "content": m.content} for m in messages]
        return client.chat.completions.create(  # type: ignore[no-any-return]
            model=self._model,
            messages=litellm_messages,
            response_model=CommitAnalysis,
            max_tokens=_ANALYSIS_MAX_TOKENS,
        )
