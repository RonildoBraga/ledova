import json
from unittest.mock import MagicMock, PropertyMock, patch

import requests
from django.test import SimpleTestCase

from authentication.services.v2_delivery_provider import V2DeliveryProviderResult
from integrations.sendgrid_email.v2_delivery import (
    V2SendGridConfiguration,
    send_v2_sendgrid_email,
)


class V2SendGridDeliveryTests(SimpleTestCase):
    def setUp(self):
        self.configuration = V2SendGridConfiguration(
            api_key="private-api-key",
            api_url="https://api.sendgrid.com/v3/mail/send",
            from_email="sender@example.test",
            timeout_seconds=7,
        )
        self.message = {
            "to_email": "recipient@example.test",
            "subject": "Private subject",
            "html_content": "<p>Private body</p>",
            "text_content": "Private body",
        }

    def _send(self, **overrides):
        values = {"configuration": self.configuration, **self.message, **overrides}
        return send_v2_sendgrid_email(**values)

    def test_result_type_has_only_the_frozen_members(self):
        self.assertEqual(
            [(member.name, member.value) for member in V2DeliveryProviderResult],
            [
                ("ACCEPTED", "accepted"),
                ("REJECTED", "rejected"),
                ("AMBIGUOUS", "ambiguous"),
            ],
        )

    def test_configuration_representation_is_fixed_and_redacted(self):
        self.assertEqual(repr(self.configuration), "V2SendGridConfiguration(<redacted>)")
        self.assertEqual(str(self.configuration), "V2SendGridConfiguration(<redacted>)")
        for private_value in (
            self.configuration.api_key,
            self.configuration.api_url,
            self.configuration.from_email,
        ):
            self.assertNotIn(private_value, repr(self.configuration))
            self.assertNotIn(private_value, str(self.configuration))

    @patch("integrations.sendgrid_email.v2_delivery.requests.adapters.HTTPAdapter")
    def test_transport_disables_ambient_state_and_retries(self, adapter_factory):
        adapter = MagicMock()
        response = MagicMock(status_code=202)
        adapter.send.return_value = response
        adapter_factory.return_value = adapter

        result = self._send()

        self.assertIs(result, V2DeliveryProviderResult.ACCEPTED)
        adapter_factory.assert_called_once_with(max_retries=0)
        adapter.send.assert_called_once()
        self.assertEqual(
            adapter.send.call_args.kwargs,
            {
                "timeout": (self.configuration.timeout_seconds, self.configuration.timeout_seconds),
                "stream": True,
                "verify": True,
                "cert": None,
                "proxies": {},
            },
        )
        adapter.close.assert_called_once_with()
        response.close.assert_called_once_with()

    @patch("integrations.sendgrid_email.v2_delivery.requests.adapters.HTTPAdapter")
    def test_transport_construction_failure_rejects_before_send(self, adapter_factory):
        adapter_factory.side_effect = RuntimeError("private construction failure")

        with self.assertNoLogs(level="DEBUG"):
            result = self._send()

        self.assertIs(result, V2DeliveryProviderResult.REJECTED)

    @patch("requests.utils.get_environ_proxies", side_effect=AssertionError("environment proxies read"))
    @patch("requests.sessions.get_netrc_auth", side_effect=AssertionError("netrc read"))
    @patch("integrations.sendgrid_email.v2_delivery.requests.adapters.HTTPAdapter.send")
    def test_transport_does_not_consult_environment_or_netrc(self, send, _netrc, _proxies):
        send.return_value = MagicMock(status_code=202)

        self.assertIs(self._send(), V2DeliveryProviderResult.ACCEPTED)
        send.assert_called_once()

    @patch("integrations.sendgrid_email.v2_delivery.requests.adapters.HTTPAdapter.send")
    def test_only_explicit_202_is_accepted(self, post):
        for status_code, expected in (
            (100, V2DeliveryProviderResult.AMBIGUOUS),
            (199, V2DeliveryProviderResult.AMBIGUOUS),
            (200, V2DeliveryProviderResult.AMBIGUOUS),
            (201, V2DeliveryProviderResult.AMBIGUOUS),
            (202, V2DeliveryProviderResult.ACCEPTED),
            (203, V2DeliveryProviderResult.AMBIGUOUS),
            (299, V2DeliveryProviderResult.AMBIGUOUS),
            (300, V2DeliveryProviderResult.AMBIGUOUS),
            (301, V2DeliveryProviderResult.AMBIGUOUS),
            (302, V2DeliveryProviderResult.AMBIGUOUS),
            (303, V2DeliveryProviderResult.AMBIGUOUS),
            (307, V2DeliveryProviderResult.AMBIGUOUS),
            (308, V2DeliveryProviderResult.AMBIGUOUS),
            (399, V2DeliveryProviderResult.AMBIGUOUS),
            (400, V2DeliveryProviderResult.REJECTED),
            (408, V2DeliveryProviderResult.REJECTED),
            (429, V2DeliveryProviderResult.REJECTED),
            (499, V2DeliveryProviderResult.REJECTED),
            (500, V2DeliveryProviderResult.AMBIGUOUS),
            (599, V2DeliveryProviderResult.AMBIGUOUS),
            (600, V2DeliveryProviderResult.AMBIGUOUS),
        ):
            with self.subTest(status_code=status_code):
                response = MagicMock(status_code=status_code)
                post.return_value = response

                self.assertIs(self._send(), expected)
                response.close.assert_called_once_with()
                post.reset_mock()

    @patch("integrations.sendgrid_email.v2_delivery.requests.adapters.HTTPAdapter.send")
    def test_redirect_response_body_is_never_consumed(self, send):
        for status_code in (301, 302, 303, 307, 308):
            with self.subTest(status_code=status_code):
                raw = MagicMock()
                raw.read.side_effect = AssertionError("redirect body read")
                response = requests.Response()
                response.status_code = status_code
                response.headers["Location"] = "https://redirect.example.test/private"
                response.raw = raw
                send.return_value = response

                self.assertIs(self._send(), V2DeliveryProviderResult.AMBIGUOUS)
                send.assert_called_once()
                raw.read.assert_not_called()
                raw.close.assert_called_once_with()
                send.reset_mock()

    @patch("integrations.sendgrid_email.v2_delivery.requests.adapters.HTTPAdapter.send")
    def test_non_integer_statuses_are_ambiguous(self, post):
        for status_code in (True, 202.0, "202", None):
            with self.subTest(status_code=status_code):
                post.return_value = MagicMock(status_code=status_code)
                self.assertIs(self._send(), V2DeliveryProviderResult.AMBIGUOUS)
                post.reset_mock()

    @patch("integrations.sendgrid_email.v2_delivery.requests.adapters.HTTPAdapter.send")
    def test_exact_eu_endpoint_is_allowed(self, post):
        post.return_value = MagicMock(status_code=202)
        configuration = V2SendGridConfiguration(
            api_key="private-api-key",
            api_url="https://api.eu.sendgrid.com/v3/mail/send",
            from_email="sender@example.test",
            timeout_seconds=10,
        )

        self.assertIs(
            self._send(configuration=configuration),
            V2DeliveryProviderResult.ACCEPTED,
        )
        self.assertEqual(post.call_args.args[0].url, configuration.api_url)

    @patch("integrations.sendgrid_email.v2_delivery.requests.adapters.HTTPAdapter.send")
    def test_request_is_single_nonredirecting_streamed_post(self, post):
        response = MagicMock(status_code=202)
        post.return_value = response

        result = self._send()

        self.assertIs(result, V2DeliveryProviderResult.ACCEPTED)
        post.assert_called_once()
        prepared_request = post.call_args.args[0]
        self.assertEqual(prepared_request.method, "POST")
        self.assertEqual(prepared_request.url, self.configuration.api_url)
        self.assertEqual(prepared_request.headers["Accept"], "application/json")
        self.assertEqual(prepared_request.headers["Authorization"], f"Bearer {self.configuration.api_key}")
        self.assertEqual(
            json.loads(prepared_request.body),
            {
                "personalizations": [{"to": [{"email": self.message["to_email"]}]}],
                "from": {"email": self.configuration.from_email},
                "subject": self.message["subject"],
                "content": [
                    {"type": "text/plain", "value": self.message["text_content"]},
                    {"type": "text/html", "value": self.message["html_content"]},
                ],
            },
        )
        self.assertEqual(
            post.call_args.kwargs,
            {
                "timeout": (self.configuration.timeout_seconds, self.configuration.timeout_seconds),
                "stream": True,
                "verify": True,
                "cert": None,
                "proxies": {},
            },
        )
        response.close.assert_called_once_with()

    @patch("integrations.sendgrid_email.v2_delivery.requests.adapters.HTTPAdapter.send")
    def test_optional_plain_text_is_omitted_without_mutating_content(self, post):
        post.return_value = MagicMock(status_code=202)

        result = self._send(text_content=None)

        self.assertIs(result, V2DeliveryProviderResult.ACCEPTED)
        self.assertEqual(
            json.loads(post.call_args.args[0].body)["content"],
            [{"type": "text/html", "value": self.message["html_content"]}],
        )

    @patch("integrations.sendgrid_email.v2_delivery.requests.adapters.HTTPAdapter.send")
    def test_explicit_empty_plain_text_is_preserved(self, post):
        post.return_value = MagicMock(status_code=202)

        result = self._send(text_content="")

        self.assertIs(result, V2DeliveryProviderResult.ACCEPTED)
        self.assertEqual(
            json.loads(post.call_args.args[0].body)["content"][0],
            {"type": "text/plain", "value": ""},
        )

    @patch("integrations.sendgrid_email.v2_delivery.requests.adapters.HTTPAdapter.send")
    def test_meaningful_subject_and_body_whitespace_is_preserved(self, post):
        post.return_value = MagicMock(status_code=202)
        subject = "  Private subject\n"
        html_content = "\n<p>Private body</p>  "

        result = self._send(subject=subject, html_content=html_content)

        self.assertIs(result, V2DeliveryProviderResult.ACCEPTED)
        payload = json.loads(post.call_args.args[0].body)
        self.assertEqual(payload["subject"], subject)
        self.assertEqual(payload["content"][-1]["value"], html_content)

    @patch("integrations.sendgrid_email.v2_delivery.requests.adapters.HTTPAdapter.send")
    def test_local_configuration_failures_reject_before_http(self, post):
        class ConfigurationSubclass(V2SendGridConfiguration):
            pass

        invalid_configurations = (
            None,
            V2SendGridConfiguration("", self.configuration.api_url, self.configuration.from_email, 7),
            V2SendGridConfiguration(" key", self.configuration.api_url, self.configuration.from_email, 7),
            V2SendGridConfiguration("key\n", self.configuration.api_url, self.configuration.from_email, 7),
            V2SendGridConfiguration("key", "", self.configuration.from_email, 7),
            V2SendGridConfiguration("key", [], self.configuration.from_email, 7),
            V2SendGridConfiguration("key", "http://api.sendgrid.com/v3/mail/send", self.configuration.from_email, 7),
            V2SendGridConfiguration("key", "https://example.test/v3/mail/send", self.configuration.from_email, 7),
            V2SendGridConfiguration("key", "https://api.sendgrid.com/v3/mail/send/", self.configuration.from_email, 7),
            V2SendGridConfiguration(
                "key", "https://api.sendgrid.com:443/v3/mail/send", self.configuration.from_email, 7
            ),
            V2SendGridConfiguration(
                "key", "https://user@api.sendgrid.com/v3/mail/send", self.configuration.from_email, 7
            ),
            V2SendGridConfiguration("key", f"{self.configuration.api_url}?value=1", self.configuration.from_email, 7),
            V2SendGridConfiguration("key", f" {self.configuration.api_url}", self.configuration.from_email, 7),
            V2SendGridConfiguration("key", self.configuration.api_url, "invalid", 7),
            V2SendGridConfiguration("key", self.configuration.api_url, "Sender@example.test", 7),
            V2SendGridConfiguration("key", self.configuration.api_url, self.configuration.from_email, 0),
            V2SendGridConfiguration("key", self.configuration.api_url, self.configuration.from_email, -1),
            V2SendGridConfiguration("key", self.configuration.api_url, self.configuration.from_email, float("nan")),
            V2SendGridConfiguration("key", self.configuration.api_url, self.configuration.from_email, float("inf")),
            V2SendGridConfiguration("key", self.configuration.api_url, self.configuration.from_email, 11),
            V2SendGridConfiguration("key", self.configuration.api_url, self.configuration.from_email, 10**1000),
            V2SendGridConfiguration("key", self.configuration.api_url, self.configuration.from_email, True),
            ConfigurationSubclass("key", self.configuration.api_url, self.configuration.from_email, 7),
        )
        for configuration in invalid_configurations:
            with self.subTest(configuration=repr(configuration)):
                self.assertIs(
                    self._send(configuration=configuration),
                    V2DeliveryProviderResult.REJECTED,
                )
        post.assert_not_called()

    @patch("integrations.sendgrid_email.v2_delivery.requests.adapters.HTTPAdapter.send")
    def test_local_message_failures_reject_before_http(self, post):
        invalid_messages = (
            {"to_email": ""},
            {"to_email": "invalid"},
            {"to_email": " recipient@example.test"},
            {"to_email": "Recipient@example.test"},
            {"to_email": "récipient@example.test"},
            {"subject": ""},
            {"subject": " \n\t"},
            {"subject": object()},
            {"html_content": ""},
            {"html_content": " \n\t"},
            {"html_content": object()},
            {"text_content": object()},
        )
        for invalid_message in invalid_messages:
            with self.subTest(fields=tuple(invalid_message)):
                self.assertIs(
                    self._send(**invalid_message),
                    V2DeliveryProviderResult.REJECTED,
                )
        post.assert_not_called()

    @patch("integrations.sendgrid_email.v2_delivery.requests.adapters.HTTPAdapter.send")
    def test_request_failures_are_ambiguous_and_redacted(self, post):
        private_exception = "private provider failure"
        for exception in (
            requests.ConnectTimeout(private_exception),
            requests.ReadTimeout(private_exception),
            requests.Timeout(private_exception),
            requests.ConnectionError(private_exception),
            requests.exceptions.SSLError(private_exception),
            requests.exceptions.ProxyError(private_exception),
            requests.RequestException(private_exception),
            RuntimeError(private_exception),
        ):
            with self.subTest(exception=type(exception).__name__):
                post.side_effect = exception
                with self.assertNoLogs(level="DEBUG"):
                    result = self._send()
                self.assertIs(result, V2DeliveryProviderResult.AMBIGUOUS)
                self.assertNotIn(private_exception, repr(result))
                self.assertNotIn(private_exception, str(result))
                post.reset_mock(side_effect=True)

    @patch("integrations.sendgrid_email.v2_delivery.requests.adapters.HTTPAdapter.send")
    @patch("integrations.sendgrid_email.v2_delivery.requests.Request.prepare")
    def test_local_request_construction_failures_are_rejected(self, prepare, send):
        private_exception = "private local failure"
        for exception_type in (
            requests.exceptions.InvalidHeader,
            requests.exceptions.InvalidSchema,
            requests.exceptions.InvalidURL,
            requests.exceptions.MissingSchema,
            requests.exceptions.URLRequired,
        ):
            with self.subTest(exception=exception_type.__name__):
                prepare.side_effect = exception_type(private_exception)
                with self.assertNoLogs(level="DEBUG"):
                    result = self._send()
                self.assertIs(result, V2DeliveryProviderResult.REJECTED)
                self.assertNotIn(private_exception, repr(result))
                prepare.reset_mock(side_effect=True)
        send.assert_not_called()

    @patch("integrations.sendgrid_email.v2_delivery.requests.adapters.HTTPAdapter.send")
    def test_noncanonical_response_is_ambiguous_without_reading_provider_data(self, post):
        response = MagicMock()
        type(response).status_code = PropertyMock(return_value="202")
        type(response).text = PropertyMock(side_effect=AssertionError("body read"))
        type(response).content = PropertyMock(side_effect=AssertionError("content read"))
        type(response).headers = PropertyMock(side_effect=AssertionError("headers read"))
        type(response).history = PropertyMock(side_effect=AssertionError("history read"))
        type(response).request = PropertyMock(side_effect=AssertionError("request read"))
        type(response).reason = PropertyMock(side_effect=AssertionError("reason read"))
        response.json.side_effect = AssertionError("json read")
        post.return_value = response

        self.assertIs(self._send(), V2DeliveryProviderResult.AMBIGUOUS)
        response.close.assert_called_once_with()

    @patch("integrations.sendgrid_email.v2_delivery.requests.adapters.HTTPAdapter.send")
    def test_response_access_failure_is_ambiguous_but_close_failure_preserves_status(self, post):
        status_failure = MagicMock()
        type(status_failure).status_code = PropertyMock(side_effect=RuntimeError("private status failure"))
        close_failure = MagicMock(status_code=202)
        close_failure.close.side_effect = RuntimeError("private close failure")

        post.return_value = status_failure
        with self.assertNoLogs(level="DEBUG"):
            self.assertIs(self._send(), V2DeliveryProviderResult.AMBIGUOUS)
        status_failure.close.assert_called_once_with()

        post.reset_mock()
        post.return_value = close_failure
        with self.assertNoLogs(level="DEBUG"):
            self.assertIs(self._send(), V2DeliveryProviderResult.ACCEPTED)
        close_failure.close.assert_called_once_with()

    @patch("integrations.sendgrid_email.v2_delivery.requests.adapters.HTTPAdapter.send")
    def test_provider_body_headers_and_message_id_are_not_observed_or_returned(self, post):
        response = MagicMock(status_code=202)
        type(response).text = PropertyMock(side_effect=AssertionError("private provider body"))
        type(response).headers = PropertyMock(side_effect=AssertionError("private-message-id"))
        post.return_value = response

        with self.assertNoLogs(level="DEBUG"):
            result = self._send()

        self.assertIs(result, V2DeliveryProviderResult.ACCEPTED)
        rendered = f"{result!r} {result}"
        for private_value in (
            "private provider body",
            "private-message-id",
            self.configuration.api_key,
            self.message["to_email"],
            self.message["subject"],
            self.message["html_content"],
            self.message["text_content"],
        ):
            self.assertNotIn(private_value, rendered)
