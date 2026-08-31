from unittest.mock import MagicMock, patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings
from openai import OpenAIError
from pydantic import BaseModel

from integrations.llm_extract.client import LlmExtractClient, _validate_local_base_url
from integrations.llm_extract.exceptions import LlmExtractError, LlmExtractValidationError


class ExampleExtraction(BaseModel):
    amount: int


class LlmExtractClientBoundaryTests(SimpleTestCase):
    def test_local_endpoints_are_allowed(self) -> None:
        for value in (
            "http://localhost:11434/v1/",
            "http://127.0.0.1:11434/v1",
            "http://[::1]:11434/v1",
            "http://host.docker.internal:11434/v1",
        ):
            with self.subTest(value=value):
                self.assertEqual(_validate_local_base_url(value), value.rstrip("/"))

    def test_remote_or_credentialed_endpoints_are_rejected(self) -> None:
        for value in (
            "https://example.test/v1",
            "http://user:password@localhost:11434/v1",
            "file:///tmp/socket",
            "not-a-url",
        ):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                _validate_local_base_url(value)

    @override_settings(LLM_BASE_URL="http://localhost:11434/v1", LLM_MODEL="local-model")
    def test_local_client_uses_ollama_placeholder_key(self) -> None:
        client = LlmExtractClient()
        self.assertEqual(client._get_api_key(), "ollama")

    @override_settings(LLM_BASE_URL="http://localhost:11434/v1", LLM_MODEL="")
    def test_blank_model_is_rejected(self) -> None:
        with self.assertRaises(ImproperlyConfigured):
            LlmExtractClient()

    @override_settings(LLM_BASE_URL="http://localhost:11434/v1", LLM_MODEL="local-model")
    @patch("integrations.llm_extract.client.OpenAI")
    def test_upstream_error_is_not_exposed(self, openai_class: MagicMock) -> None:
        openai_class.return_value.chat.completions.create.side_effect = OpenAIError("private upstream detail")

        with self.assertRaises(LlmExtractError) as raised:
            LlmExtractClient().extract(image_bytes=b"image", prompt="prompt", schema=ExampleExtraction)

        self.assertNotIn("private upstream detail", str(raised.exception.detail))

    @override_settings(LLM_BASE_URL="http://localhost:11434/v1", LLM_MODEL="local-model")
    @patch("integrations.llm_extract.client.logger")
    @patch("integrations.llm_extract.client.OpenAI")
    def test_invalid_private_output_is_not_logged(
        self,
        openai_class: MagicMock,
        logger: MagicMock,
    ) -> None:
        message = MagicMock(content='{"amount": "private-value"}')
        openai_class.return_value.chat.completions.create.return_value = MagicMock(choices=[MagicMock(message=message)])

        with self.assertRaises(LlmExtractValidationError) as raised:
            LlmExtractClient().extract(image_bytes=b"image", prompt="prompt", schema=ExampleExtraction)

        logged_arguments = repr(logger.warning.call_args)
        self.assertNotIn("private-value", logged_arguments)
        self.assertNotIn("private-value", str(raised.exception.detail))
