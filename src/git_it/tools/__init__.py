"""Shared read-only domain tool layer (spec 012 / refactor of spec 011).

Plain functions over the analyzed domain that both the MCP server
(`git_it.mcp.server`) and the in-app chat (GitItGPT) call — one source of truth.
All functions are read-only and return the same response models as the REST API.
"""

from git_it.tools import registry

__all__ = ["registry"]
