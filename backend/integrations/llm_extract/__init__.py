"""
LLM extraction client.

Backend-side wrapper around a local OpenAI-compatible chat completions
endpoint. `LLM_BASE_URL` must resolve to an explicitly allowed loopback or
host-container address; remote hosted endpoints are intentionally rejected.
"""

from integrations.llm_extract.client import LlmExtractClient
from integrations.llm_extract.exceptions import (
    LlmExtractError,
    LlmExtractValidationError,
)

__all__ = ["LlmExtractClient", "LlmExtractError", "LlmExtractValidationError"]
