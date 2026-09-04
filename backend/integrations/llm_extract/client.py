"""
OpenAI-compatible chat client for document extraction.

The documents are private financial records, so only loopback and host-container endpoints are accepted.
Ollama requires a non-empty API key but ignores its value.
"""

from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from typing import Type
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from openai import OpenAI, OpenAIError
from pydantic import BaseModel, ValidationError

from integrations.llm_extract.exceptions import (
    LlmExtractError,
    LlmExtractValidationError,
)

logger = logging.getLogger(__name__)

_LOCAL_LLM_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal"})


def _validate_local_base_url(value: str) -> str:
    candidate = value.strip().rstrip("/")
    parsed = urlsplit(candidate)

    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in _LOCAL_LLM_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ImproperlyConfigured("LLM_BASE_URL must use a local loopback or host.docker.internal endpoint")

    return candidate


@dataclass
class ExtractionResult:
    parsed: BaseModel
    raw_output: str
    duration_ms: int
    model_used: str


class LlmExtractClient:

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout_s: float = 120.0,
    ) -> None:
        self.base_url = _validate_local_base_url(base_url or settings.LLM_BASE_URL)
        self.model = (model or settings.LLM_MODEL).strip()
        if not self.model:
            raise ImproperlyConfigured("LLM_MODEL must not be blank")
        self.timeout_s = timeout_s

    def _get_api_key(self) -> str:
        return "ollama"

    def extract(
        self,
        *,
        image_bytes: bytes,
        prompt: str,
        schema: Type[BaseModel],
    ) -> ExtractionResult:
        """One image plus prompt in, the schema-validated object plus the raw reply and timing out."""
        b64 = base64.b64encode(image_bytes).decode("ascii")

        client = OpenAI(
            base_url=self.base_url,
            api_key=self._get_api_key(),
            timeout=self.timeout_s,
        )

        started = time.monotonic()
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{b64}",
                                },
                            },
                        ],
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
        except OpenAIError as e:
            logger.warning("llm_extract: local upstream call failed")
            raise LlmExtractError() from e
        duration_ms = int((time.monotonic() - started) * 1000)

        raw = response.choices[0].message.content or ""
        try:
            parsed = schema.model_validate_json(raw)
        except ValidationError as e:
            logger.warning("llm_extract: output validation failed for schema %s", schema.__name__)
            raise LlmExtractValidationError() from e

        return ExtractionResult(
            parsed=parsed,
            raw_output=raw,
            duration_ms=duration_ms,
            model_used=self.model,
        )
