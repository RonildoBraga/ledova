import hashlib
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
from django.test import SimpleTestCase, override_settings

from authentication.security.v2_access_tokens import (
    INITIAL_ACCESS_KID,
    AccessTokenConfiguration,
    AccessTokenConfigurationError,
    AccessTokenError,
    AccessTokenIssued,
    issue_access_token,
    resolve_access_config,
    resolve_access_expiry,
    verify_access_token,
)
from authentication.security.v2_credentials import V2KeyMaterial


@override_settings(SECRET_KEY="django-secret-distinct-from-v2-access-keys")
class V2AccessTokenTest(SimpleTestCase):
    def setUp(self):
        self.now = datetime(2030, 1, 2, 3, 4, 5, 987654, tzinfo=timezone.utc)
        self.session_id = uuid.UUID("00000000-0000-4000-8000-000000000001")
        self.token_id = uuid.UUID("00000000-0000-4000-8000-000000000002")
        self.keys = V2KeyMaterial(access_signing_key=b"a" * 32, refresh_hmac_key=b"r" * 32)
        self.config = resolve_access_config(self.keys)

    def issue(self, *, user_id=7, token_id=None, lifetime=timedelta(minutes=15), configuration=None):
        session_expires_at = self.now + timedelta(days=30)
        expires_at = resolve_access_expiry(
            self.now,
            session_expires_at,
            lifetime,
        )
        return issue_access_token(
            user_id,
            self.session_id,
            issued_at=self.now,
            expires_at=expires_at,
            session_expires_at=session_expires_at,
            token_id=token_id or self.token_id,
            configuration=configuration or self.config,
        )

    def signed(self, payload, *, key=None, headers=None, algorithm="HS256"):
        return jwt.encode(
            payload,
            key or self.keys.access_signing_key,
            algorithm=algorithm,
            headers=headers or {"typ": "at+jwt", "kid": INITIAL_ACCESS_KID},
        )

    def payload(self, token=None):
        token = token or self.issue().access_token
        return jwt.decode(
            token,
            self.keys.access_signing_key,
            algorithms=["HS256"],
            audience="urn:ledova:api",
            issuer="urn:ledova:auth",
            options={"verify_iat": False, "verify_exp": False, "strict_aud": True},
        )

    def assert_invalid(self, token, *, configuration=None, clock=None):
        arguments = {
            "configuration": configuration or self.config,
            "clock": clock or (lambda: self.now),
        }
        with self.assertRaisesMessage(AccessTokenError, "Invalid v2 access token."):
            verify_access_token(token, **arguments)

    def test_exact_profile_is_deterministic_verifiable_and_redacted(self):
        result = self.issue()
        payload = self.payload(result.access_token)
        claims = verify_access_token(
            result.access_token,
            configuration=self.config,
            clock=lambda: self.now,
        )

        self.assertIsInstance(result, AccessTokenIssued)
        self.assertEqual(
            jwt.get_unverified_header(result.access_token),
            {"alg": "HS256", "kid": INITIAL_ACCESS_KID, "typ": "at+jwt"},
        )
        self.assertEqual(
            payload,
            {
                "typ": "access",
                "ver": 2,
                "sub": "7",
                "sid": str(self.session_id),
                "jti": str(self.token_id),
                "iat": 1893553445,
                "exp": 1893554345,
                "iss": "urn:ledova:auth",
                "aud": "urn:ledova:api",
            },
        )
        self.assertEqual(result.access_expires_at, datetime(2030, 1, 2, 3, 19, 5, tzinfo=timezone.utc))
        self.assertEqual(claims.user_id, 7)
        self.assertEqual(claims.session_id, self.session_id)
        self.assertEqual(claims.token_id, self.token_id)
        self.assertEqual(claims.issued_at, datetime(2030, 1, 2, 3, 4, 5, tzinfo=timezone.utc))
        self.assertEqual(claims.expires_at, result.access_expires_at)
        self.assertEqual(
            hashlib.sha256(result.access_token.encode("ascii")).hexdigest(),
            "2a997992e98c712c2e5bc0be152469bd8c7e20dbaae80d1c0d7f6e5058bee43f",
        )
        self.assertNotIn(result.access_token, repr(result))
        self.assertNotIn(str(self.session_id), repr(claims))

    def test_configuration_is_immutable_rotatable_separated_and_redacted(self):
        old_key = b"o" * 32
        current_key = b"n" * 32
        material = V2KeyMaterial(access_signing_key=current_key, refresh_hmac_key=b"r" * 32)
        rotated = resolve_access_config(
            material,
            current_kid="ledova-v2-access-hs256-2",
            verifier_keys={
                INITIAL_ACCESS_KID: old_key,
                "ledova-v2-access-hs256-2": current_key,
            },
        )
        old_config = resolve_access_config(V2KeyMaterial(access_signing_key=old_key, refresh_hmac_key=b"r" * 32))
        old_token = self.issue(configuration=old_config).access_token
        current_token = self.issue(configuration=rotated).access_token

        self.assertEqual(jwt.get_unverified_header(current_token)["kid"], "ledova-v2-access-hs256-2")
        self.assertEqual(verify_access_token(old_token, configuration=rotated, clock=lambda: self.now).user_id, 7)
        self.assertEqual(verify_access_token(current_token, configuration=rotated, clock=lambda: self.now).user_id, 7)
        self.assertNotIn(current_key.decode("ascii"), repr(rotated))
        with self.assertRaises(TypeError):
            rotated.verifier_keys["new"] = b"x" * 32
        with self.assertRaisesMessage(
            AccessTokenConfigurationError,
            "Invalid v2 access token configuration.",
        ):
            AccessTokenConfiguration(
                current_kid=INITIAL_ACCESS_KID,
                signing_key=self.keys.refresh_hmac_key,
                verifier_keys={INITIAL_ACCESS_KID: self.keys.refresh_hmac_key},
            )
        with self.assertRaisesMessage(
            AccessTokenConfigurationError,
            "Invalid v2 access token configuration.",
        ):
            replace(
                self.config,
                signing_key=self.keys.refresh_hmac_key,
                verifier_keys={INITIAL_ACCESS_KID: self.keys.refresh_hmac_key},
            )

        invalid_configurations = (
            {"current_kid": "invalid kid", "verifier_keys": {"invalid kid": current_key}},
            {"current_kid": "ledova-v2-access-hs256-2", "verifier_keys": {INITIAL_ACCESS_KID: current_key}},
            {
                "current_kid": "ledova-v2-access-hs256-2",
                "verifier_keys": {INITIAL_ACCESS_KID: current_key, "ledova-v2-access-hs256-2": current_key},
            },
            {"current_kid": "ledova-v2-access-hs256-2", "verifier_keys": {"ledova-v2-access-hs256-2": b"x"}},
        )
        for case in invalid_configurations:
            with self.subTest(case=case["current_kid"]):
                with self.assertRaisesMessage(
                    AccessTokenConfigurationError,
                    "Invalid v2 access token configuration.",
                ):
                    resolve_access_config(
                        material,
                        current_kid=case["current_kid"],
                        verifier_keys=case["verifier_keys"],
                    )

        for separated_key in (material.refresh_hmac_key, settings_secret_bytes()):
            with self.subTest(separated_key=separated_key[:1]):
                with self.assertRaisesMessage(
                    AccessTokenConfigurationError,
                    "Invalid v2 access token configuration.",
                ):
                    resolve_access_config(
                        material,
                        current_kid="ledova-v2-access-hs256-2",
                        verifier_keys={"ledova-v2-access-hs256-2": current_key, "old": separated_key},
                    )

    def test_expiry_resolution_shortens_caps_floors_and_refuses_empty_window(self):
        shortened = resolve_access_expiry(self.now, self.now + timedelta(days=1), timedelta(seconds=30))
        capped = resolve_access_expiry(self.now, self.now + timedelta(seconds=4, microseconds=100000))
        refused = resolve_access_expiry(self.now, self.now + timedelta(microseconds=1000))

        self.assertEqual(shortened, datetime(2030, 1, 2, 3, 4, 35, tzinfo=timezone.utc))
        self.assertEqual(capped, datetime(2030, 1, 2, 3, 4, 10, tzinfo=timezone.utc))
        self.assertIsNone(refused)

        for lifetime in (
            timedelta(0),
            timedelta(microseconds=999999),
            timedelta(seconds=-1),
            timedelta(seconds=901),
        ):
            with self.subTest(lifetime=lifetime):
                with self.assertRaisesMessage(AccessTokenError, "Invalid v2 access token."):
                    resolve_access_expiry(self.now, self.now + timedelta(days=1), lifetime)

    def test_issuer_rejects_invalid_subject_identifier_times_and_configuration(self):
        expires_at = resolve_access_expiry(self.now, self.now + timedelta(days=1))
        invalid_cases = (
            {"user_id": True},
            {"user_id": 0},
            {"user_id": 1 << 63},
            {"session_id": str(self.session_id)},
            {"token_id": uuid.UUID(int=1)},
            {"issued_at": self.now.replace(tzinfo=None)},
            {"expires_at": self.now},
            {"expires_at": self.now + timedelta(seconds=901)},
            {"configuration": object()},
        )
        base = {
            "user_id": 7,
            "session_id": self.session_id,
            "issued_at": self.now,
            "expires_at": expires_at,
            "session_expires_at": self.now + timedelta(days=1),
            "token_id": self.token_id,
            "configuration": self.config,
        }
        for override in invalid_cases:
            arguments = {**base, **override}
            with self.subTest(field=next(iter(override))):
                expected = AccessTokenConfigurationError if "configuration" in override else AccessTokenError
                with self.assertRaises(expected):
                    issue_access_token(**arguments)

        with self.assertRaises(AccessTokenError):
            issue_access_token(
                **{
                    **base,
                    "expires_at": self.now + timedelta(seconds=30),
                    "session_expires_at": self.now + timedelta(seconds=10),
                }
            )

    def test_verifier_rejects_malformed_or_oversized_input_before_header_parsing(self):
        valid = self.issue().access_token
        invalid_tokens = (
            "é.a.b",
            "a" * 1025,
            "a.b",
            "a..b",
            valid + "=",
            valid.rsplit(".", 1)[0] + ".not+base64url",
            b"a.b.c",
        )
        for token in invalid_tokens:
            with self.subTest(token_type=type(token).__name__, length=len(token)):
                with patch("authentication.security.v2_access_tokens.jwt.get_unverified_header") as header:
                    self.assert_invalid(token)
                    header.assert_not_called()

    def test_verifier_rejects_wrong_key_header_and_registered_claims(self):
        valid = self.issue().access_token
        payload = self.payload(valid)
        cases = (
            self.signed(payload, key=b"w" * 32),
            self.signed(payload, headers={"typ": "at+jwt", "kid": "unknown"}),
            self.signed(payload, headers={"typ": "JWT", "kid": INITIAL_ACCESS_KID}),
            self.signed(payload, headers={"typ": "at+jwt", "kid": INITIAL_ACCESS_KID, "extra": "x"}),
            self.signed(payload, key=b"h" * 48, algorithm="HS384"),
            self.signed({**payload, "iss": "urn:other"}),
            self.signed({**payload, "aud": "urn:other"}),
            self.signed({**payload, "aud": ["urn:ledova:api"]}),
        )
        for token in cases:
            with self.subTest(header=jwt.get_unverified_header(token)):
                self.assert_invalid(token)

    def test_verifier_rejects_nonexact_claims_and_time_windows(self):
        payload = self.payload()
        missing = dict(payload)
        missing.pop("jti")
        cases = (
            {**payload, "extra": "x"},
            missing,
            {**payload, "typ": "refresh"},
            {**payload, "ver": True},
            {**payload, "ver": 3},
            {**payload, "sub": "01"},
            {**payload, "sub": 7},
            {**payload, "sub": str(1 << 63)},
            {**payload, "sid": str(self.session_id).replace("-", "")},
            {**payload, "jti": str(uuid.UUID(int=1))},
            {**payload, "iat": str(payload["iat"])},
            {**payload, "iat": True},
            {**payload, "exp": str(payload["exp"])},
            {**payload, "iat": payload["iat"] + 1},
            {**payload, "exp": payload["iat"]},
            {**payload, "exp": payload["iat"] + 901},
        )
        for candidate in cases:
            with self.subTest(candidate=set(candidate)):
                self.assert_invalid(self.signed(candidate))

    def test_errors_and_results_never_render_sensitive_values(self):
        token = self.issue().access_token
        self.assert_invalid(token + "sensitive-suffix")
        try:
            verify_access_token(token + "sensitive-suffix", configuration=self.config, clock=lambda: self.now)
        except AccessTokenError as error:
            rendered = f"{error!s} {error!r}"
        self.assertNotIn(token, rendered)
        self.assertNotIn(self.keys.access_signing_key.decode("ascii"), repr(self.config))


def settings_secret_bytes():
    return b"django-secret-distinct-from-v2-access-keys"
