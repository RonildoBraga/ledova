import sys
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from ledova_backend.chain_safety import parse_bitcoin_network, parse_evm_chain_id
from ledova_backend.environment import (
    assert_media_storage_is_servable,
    read_bool,
    read_choice,
    resolve_storage_backend,
)


class EnvironmentParsingTests(SimpleTestCase):
    def test_boolean_values_are_explicit(self):
        with patch.dict("os.environ", {"FEATURE": "true"}):
            self.assertTrue(read_bool("FEATURE", default=False))
        with patch.dict("os.environ", {"FEATURE": "false"}):
            self.assertFalse(read_bool("FEATURE", default=True))
        with patch.dict("os.environ", {"FEATURE": "1"}):
            with self.assertRaises(ImproperlyConfigured):
                read_bool("FEATURE", default=False)

    def test_choices_reject_unknown_values(self):
        with patch.dict("os.environ", {"STORAGE_BACKEND": "ftp"}):
            with self.assertRaises(ImproperlyConfigured):
                read_choice("STORAGE_BACKEND", choices=("local", "s3"), default="local")

    def test_local_storage_resolves_without_debug(self):
        with patch.dict("os.environ", {"STORAGE_BACKEND": "local"}):
            self.assertEqual(resolve_storage_backend(debug=False), "local")

    def test_local_storage_without_debug_is_refused_at_server_startup(self):
        with self.assertRaises(ImproperlyConfigured):
            assert_media_storage_is_servable(debug=False, storage_backend="local")

    def test_servable_media_configurations_are_accepted(self):
        assert_media_storage_is_servable(debug=True, storage_backend="local")
        assert_media_storage_is_servable(debug=False, storage_backend="s3")
        assert_media_storage_is_servable(debug=False, storage_backend="gcs")

    def test_evm_mainnets_are_rejected(self):
        for chain_id in ("1", "8453"):
            with self.subTest(chain_id=chain_id), self.assertRaises(ImproperlyConfigured):
                parse_evm_chain_id(chain_id, "CHAIN_ID")

    def test_supported_evm_testnets_and_local_chains_are_accepted(self):
        for chain_id in (1337, 31337, 84532, 11155111):
            with self.subTest(chain_id=chain_id):
                self.assertEqual(parse_evm_chain_id(str(chain_id), "CHAIN_ID"), chain_id)

    def test_bitcoin_mainnet_is_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            parse_bitcoin_network("main")
        self.assertEqual(parse_bitcoin_network("test"), "test")
        self.assertEqual(parse_bitcoin_network("regtest"), "regtest")


class AuthorizationConfigurationTests(SimpleTestCase):
    def test_authentication_uses_django_model_backend(self):
        self.assertEqual(settings.AUTHENTICATION_BACKENDS, ("django.contrib.auth.backends.ModelBackend",))

    def test_default_api_permission_requires_authentication(self):
        self.assertEqual(
            settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"],
            ("rest_framework.permissions.IsAuthenticated",),
        )


class V2WithdrawalTests(SimpleTestCase):
    def test_trusted_proxy_and_log_filter_settings_are_gone(self):
        self.assertFalse(hasattr(settings, "V2_TRUSTED_PROXY_CIDRS"))
        self.assertNotIn("filters", settings.LOGGING)
        self.assertNotIn("filters", settings.LOGGING["handlers"]["procrastinate_console"])
        self.assertNotIn("ledova_backend.logging_filters", sys.modules)

    def test_challenge_models_and_delivery_task_are_gone(self):
        from django.apps import apps

        from ledova_backend.procrastinate_app import app

        names = {model.__name__ for model in apps.get_app_config("authentication").get_models()}
        self.assertEqual(names, {"CustomUser"})
        self.assertNotIn("authentication.deliver_v2_challenge", app.tasks)

    def test_session_core_modules_and_key_material_are_gone(self):
        self.assertIsNotNone(find_spec("authentication.email"))
        for module in ("authentication.services.v2_sessions", "authentication.services.v2_access"):
            with self.subTest(module=module):
                self.assertIsNone(find_spec(module))
        env_example = (Path(settings.BASE_DIR) / ".env.example").read_text()
        self.assertNotIn("V2_ACCESS_SIGNING_KEY_B64", env_example)
        self.assertNotIn("V2_REFRESH_HMAC_KEY_B64", env_example)


class LoggingTests(SimpleTestCase):
    def test_modules_log_under_their_own_name_to_the_root_console_handler(self):
        self.assertEqual(settings.LOGGING["root"], {"handlers": ["console"], "level": "INFO"})
        self.assertNotIn("ledova_backend", settings.LOGGING["loggers"])
        self.assertIn("{name}", settings.LOGGING["formatters"]["verbose"]["format"])
        self.assertIsNone(find_spec("shared.utils.logging_utils"))
