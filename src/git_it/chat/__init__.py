"""GitItGPT — in-dashboard agentic chat over the shared read-only tool layer.

`ChatService` runs a bounded LLM tool-calling loop against `git_it.tools.registry`,
scoped to a single repository. The LLM is injected as a thin protocol so tests are
deterministic and network-free (spec 012).
"""

from git_it.chat.service import ChatResult, ChatService

__all__ = ["ChatResult", "ChatService"]
