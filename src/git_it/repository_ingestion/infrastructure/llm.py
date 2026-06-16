from git_it.repository_ingestion.application.ports import LLMMessage

_DEFAULT_MODEL = "anthropic/claude-haiku-4-5-20251001"
_DEFAULT_MAX_TOKENS = 4096


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
