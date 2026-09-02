import base64
import hashlib
import hmac
import os
import uuid
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from authentication.security.v2_credentials import (
    V2KeyMaterial,
    V2KeyMaterialError,
    load_v2_key_material,
    refresh_secret_digest,
    refresh_secret_matches,
)


def encoded(value):
    return base64.urlsafe_b64encode(value).decode("ascii")


@override_settings(SECRET_KEY="django-secret-distinct-from-v2-keys")
class V2KeyMaterialTest(SimpleTestCase):
    access_key = b"a" * 32
    refresh_key = b"r" * 32

    def setUp(self):
        super().setUp()
        environment = patch.dict(os.environ, {}, clear=False)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("V2_ACCESS_SIGNING_KEY_B64", None)
        os.environ.pop("V2_REFRESH_HMAC_KEY_B64", None)

    def configure(self, access_key=None, refresh_key=None):
        os.environ["V2_ACCESS_SIGNING_KEY_B64"] = encoded(access_key or self.access_key)
        os.environ["V2_REFRESH_HMAC_KEY_B64"] = encoded(refresh_key or self.refresh_key)

    def assert_configuration_rejected(self, *sensitive_values):
        with self.assertRaises(V2KeyMaterialError) as raised:
            load_v2_key_material()

        rendered = f"{raised.exception!s} {raised.exception!r}"
        self.assertEqual(str(raised.exception), "Invalid v2 authentication key configuration.")
        for sensitive_value in sensitive_values:
            self.assertNotIn(sensitive_value, rendered)

    def test_valid_keys_load_only_when_requested_and_have_a_redacted_repr(self):
        self.configure()

        material = load_v2_key_material()

        self.assertEqual(material.access_signing_key, self.access_key)
        self.assertEqual(material.refresh_hmac_key, self.refresh_key)
        self.assertEqual(
            repr(material),
            "V2KeyMaterial(access_signing_key=<redacted>, refresh_hmac_key=<redacted>)",
        )
        self.assertNotIn(self.access_key.decode("ascii"), repr(material))
        self.assertNotIn(self.refresh_key.decode("ascii"), repr(material))

    def test_each_missing_key_is_rejected_without_disclosing_the_present_key(self):
        configured_values = {
            "V2_ACCESS_SIGNING_KEY_B64": encoded(self.access_key),
            "V2_REFRESH_HMAC_KEY_B64": encoded(self.refresh_key),
        }

        for missing_name in configured_values:
            with self.subTest(missing_name=missing_name):
                os.environ.update(configured_values)
                os.environ.pop(missing_name)
                present_value = next(value for name, value in configured_values.items() if name != missing_name)
                self.assert_configuration_rejected(present_value)

    def test_malformed_keys_are_rejected_without_disclosing_input(self):
        self.configure()
        malformed_values = ["not+base64/value=", "contains whitespace", "sensitive-☃-value"]

        for malformed_value in malformed_values:
            with self.subTest(malformed_value=malformed_value):
                os.environ["V2_ACCESS_SIGNING_KEY_B64"] = malformed_value
                self.assert_configuration_rejected(malformed_value)

    def test_noncanonical_base64url_is_rejected_without_disclosing_input(self):
        self.configure()
        canonical = encoded(b"\x00" * 32)
        noncanonical = f"{canonical[:-2]}B="
        os.environ["V2_ACCESS_SIGNING_KEY_B64"] = noncanonical

        self.assert_configuration_rejected(noncanonical)

    def test_short_key_is_rejected_without_disclosing_input(self):
        self.configure()
        short_value = encoded(b"short-key-material")
        os.environ["V2_ACCESS_SIGNING_KEY_B64"] = short_value

        self.assert_configuration_rejected(short_value)

    def test_equal_keys_are_rejected_without_disclosing_input(self):
        equal_value = encoded(self.access_key)
        self.configure(refresh_key=self.access_key)

        self.assert_configuration_rejected(equal_value)

    def test_each_key_is_rejected_when_it_matches_django_secret_key(self):
        django_secret = "django-secret-key-that-must-not-be-reused"
        secret_bytes = django_secret.encode("utf-8")

        with override_settings(SECRET_KEY=django_secret):
            for field, access_key, refresh_key in (
                ("access", secret_bytes, self.refresh_key),
                ("refresh", self.access_key, secret_bytes),
            ):
                with self.subTest(field=field):
                    self.configure(access_key=access_key, refresh_key=refresh_key)
                    self.assert_configuration_rejected(django_secret, encoded(secret_bytes))

    def test_each_key_is_rejected_when_its_encoded_value_matches_django_secret_key(self):
        for field, access_key, refresh_key in (
            ("access", self.access_key, self.refresh_key),
            ("refresh", self.access_key, self.refresh_key),
        ):
            selected_key = access_key if field == "access" else refresh_key
            for django_secret in (encoded(selected_key), encoded(selected_key).rstrip("=")):
                with self.subTest(field=field, padding=django_secret.endswith("=")):
                    self.configure(access_key=access_key, refresh_key=refresh_key)
                    with override_settings(SECRET_KEY=django_secret):
                        self.assert_configuration_rejected(django_secret)

    def test_direct_key_material_rejects_padded_and_unpadded_django_key_reuse(self):
        for django_secret in (encoded(self.access_key), encoded(self.access_key).rstrip("=")):
            with self.subTest(padding=django_secret.endswith("=")):
                with override_settings(SECRET_KEY=django_secret):
                    with self.assertRaisesMessage(
                        V2KeyMaterialError,
                        "Invalid v2 authentication key configuration.",
                    ):
                        V2KeyMaterial(
                            access_signing_key=self.access_key,
                            refresh_hmac_key=self.refresh_key,
                        )


class RefreshSecretDigestTest(SimpleTestCase):
    selector = uuid.UUID("00000000-0000-0000-0000-000000000001")
    secret = bytes(range(32))
    key = b"k" * 32

    def test_digest_is_deterministic_domain_bound_sha256(self):
        first = refresh_secret_digest(self.selector, self.secret, self.key)
        second = refresh_secret_digest(str(self.selector), self.secret, self.key)
        unscoped = hmac.new(self.key, self.selector.bytes + self.secret, hashlib.sha256).digest()

        self.assertEqual(first, second)
        self.assertEqual(
            first.hex(),
            "c550c3d730abedc007de18c0cde6f500de161ee90563f94aa6d85e37ba75ccd2",
        )
        self.assertEqual(len(first), hashlib.sha256().digest_size)
        self.assertNotEqual(first, unscoped)

    def test_digest_is_bound_to_selector_secret_and_key(self):
        digest = refresh_secret_digest(self.selector, self.secret, self.key)

        self.assertNotEqual(
            digest,
            refresh_secret_digest(uuid.UUID(int=2), self.secret, self.key),
        )
        self.assertNotEqual(digest, refresh_secret_digest(self.selector, b"x" * 32, self.key))
        self.assertNotEqual(digest, refresh_secret_digest(self.selector, self.secret, b"z" * 32))

    def test_digest_requires_exactly_32_secret_bytes_and_a_full_length_key(self):
        invalid_pairs = (
            (b"s" * 31, self.key),
            (b"s" * 33, self.key),
            (self.secret, b"k" * 31),
        )

        for secret, key in invalid_pairs:
            with self.subTest(secret_length=len(secret), key_length=len(key)):
                with self.assertRaisesMessage(ValueError, "Invalid v2 refresh credential material."):
                    refresh_secret_digest(self.selector, secret, key)

    def test_constant_time_matching_helper_accepts_only_the_bound_digest(self):
        digest = refresh_secret_digest(self.selector, self.secret, self.key)

        self.assertTrue(refresh_secret_matches(digest, self.selector, self.secret, self.key))
        self.assertFalse(refresh_secret_matches(b"x" * 32, self.selector, self.secret, self.key))
        self.assertFalse(refresh_secret_matches(digest, uuid.UUID(int=2), self.secret, self.key))
        self.assertFalse(refresh_secret_matches(digest, self.selector, b"x" * 32, self.key))
        self.assertFalse(refresh_secret_matches(digest, self.selector, self.secret, b"z" * 32))
        self.assertFalse(refresh_secret_matches(b"short", self.selector, self.secret, self.key))
