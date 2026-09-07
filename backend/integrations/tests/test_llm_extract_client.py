from unittest.mock import MagicMock, patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings
from openai import OpenAIError
from pydantic import BaseModel

from integrations.llm_extract.client import LlmExtractClient, _validate_local_base_url
from integrations.llm_extract.exceptions import (
    LlmExtractError,
    LlmExtractValidationError,
)


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

    @override_settings(LLM_EXTRA_HOSTS=[])
    def test_a_compose_service_name_is_refused_while_nobody_opted_in(self) -> None:
        with self.assertRaises(ImproperlyConfigured):
            _validate_local_base_url("http://ollama:11434/v1")

    @override_settings(LLM_EXTRA_HOSTS=["ollama"])
    def test_a_compose_service_name_is_admitted_once_it_is_named(self) -> None:
        self.assertEqual(_validate_local_base_url("http://ollama:11434/v1"), "http://ollama:11434/v1")

    @override_settings(LLM_EXTRA_HOSTS=["ollama"])
    def test_opting_one_host_in_admits_only_that_host(self) -> None:
        for value in ("http://elsewhere:11434/v1", "https://example.test/v1"):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                _validate_local_base_url(value)

    @override_settings(LLM_EXTRA_HOSTS=["http://ollama", "ollama:11434", "ollama/v1"])
    def test_an_entry_carrying_more_than_a_hostname_admits_nothing(self) -> None:
        with self.assertRaises(ImproperlyConfigured):
            _validate_local_base_url("http://ollama:11434/v1")

    @override_settings(LLM_EXTRA_HOSTS=["*"])
    def test_a_wildcard_entry_admits_nothing_because_it_names_a_host_rather_than_a_pattern(self) -> None:
        for value in ("http://ollama:11434/v1", "http://evil.test/v1", "https://example.test/v1"):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                _validate_local_base_url(value)

    @override_settings(LLM_EXTRA_HOSTS=["*"])
    def test_a_wildcard_entry_leaves_the_local_four_exactly_as_they_were(self) -> None:
        for value in ("http://localhost:11434/v1", "http://host.docker.internal:11434/v1"):
            with self.subTest(value=value):
                self.assertEqual(_validate_local_base_url(value), value)

    @override_settings(LLM_EXTRA_HOSTS=["*.internal", "ollama*", "0.0.0.0/0"])
    def test_a_glob_or_a_range_admits_nothing_because_a_host_is_matched_by_equality(self) -> None:
        for value in ("http://svc.internal:11434/v1", "http://ollama2:11434/v1", "http://10.0.0.5:11434/v1"):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                _validate_local_base_url(value)

    @override_settings(LLM_EXTRA_HOSTS=["ollama"])
    def test_the_default_four_are_still_admitted_when_a_host_is_opted_in(self) -> None:
        for value in ("http://localhost:11434/v1", "http://host.docker.internal:11434/v1"):
            with self.subTest(value=value):
                self.assertEqual(_validate_local_base_url(value), value)

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

    @override_settings(LLM_BASE_URL="http://host.docker.internal:11434/v1", LLM_MODEL="local-model")
    @patch("integrations.llm_extract.client.OpenAI")
    def test_the_refusal_names_the_setting_without_serving_its_value(self, openai_class: MagicMock) -> None:
        openai_class.return_value.chat.completions.create.side_effect = OpenAIError("private upstream detail")

        with self.assertRaises(LlmExtractError) as raised:
            LlmExtractClient().extract(image_bytes=b"image", prompt="prompt", schema=ExampleExtraction)

        served = str(raised.exception.detail)
        self.assertIn("check LLM_BASE_URL", served)
        self.assertNotIn("host.docker.internal", served)
        self.assertNotIn("private upstream detail", served)

    @override_settings(LLM_BASE_URL="http://127.0.0.1:11434/v1/sk-proj-9f3a", LLM_MODEL="local-model")
    @patch("integrations.llm_extract.client.OpenAI")
    def test_a_secret_hidden_in_the_path_is_not_served(self, openai_class: MagicMock) -> None:
        openai_class.return_value.chat.completions.create.side_effect = OpenAIError("private upstream detail")

        with self.assertRaises(LlmExtractError) as raised:
            LlmExtractClient().extract(image_bytes=b"image", prompt="prompt", schema=ExampleExtraction)

        self.assertNotIn("sk-proj-9f3a", str(raised.exception.detail))

    @override_settings(LLM_BASE_URL="http://localhost:11434/v1", LLM_MODEL="local-model")
    @patch("integrations.llm_extract.client.OpenAI")
    def test_an_unreachable_host_is_given_up_on_in_seconds_not_minutes(self, openai_class: MagicMock) -> None:
        message = MagicMock(content='{"amount": 1}')
        openai_class.return_value.chat.completions.create.return_value = MagicMock(choices=[MagicMock(message=message)])

        LlmExtractClient().extract(image_bytes=b"image", prompt="prompt", schema=ExampleExtraction)

        timeout = openai_class.call_args.kwargs["timeout"]
        self.assertEqual(timeout.connect, 5.0)
        self.assertEqual(timeout.read, 120.0)

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
