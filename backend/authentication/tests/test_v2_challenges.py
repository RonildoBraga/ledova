import base64
import hashlib
import hmac
import ipaddress
import os
import uuid
from dataclasses import FrozenInstanceError, replace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from authentication.security.v2_access_tokens import (
    INITIAL_ACCESS_KID,
    resolve_access_config,
)
from authentication.security.v2_challenges import (
    INITIAL_CHALLENGE_PROOF_KID,
    INITIAL_CHALLENGE_RATE_KID,
    ChallengeDigest,
    ChallengeKeyConfiguration,
    ChallengeKeyConfigurationError,
    ChallengeMaterialError,
    ChallengeRateDigests,
    V2ChallengeCredentialParts,
    decode_v2_password_reset_credential,
    decode_v2_pending_context,
    destination_rate_digests,
    encode_v2_password_reset_credential,
    encode_v2_pending_context,
    generate_v2_otp,
    ip_rate_digests,
    load_challenge_config,
    otp_digest,
    otp_matches,
    password_reset_digest,
    password_reset_matches,
    pending_context_digest,
    pending_context_matches,
    resolve_challenge_config,
)
from authentication.security.v2_credentials import V2KeyMaterial


def encoded(value):
    return base64.urlsafe_b64encode(value).decode("ascii")


def unpadded(value):
    return encoded(value).rstrip("=")


def framed_hmac(key, *values):
    message = b"".join(len(value).to_bytes(4, "big") + value for value in values)
    return hmac.new(key, message, hashlib.sha256).digest()


@override_settings(SECRET_KEY="django-secret-distinct-from-v2-challenge-keys")
class V2ChallengePrimitivesTest(SimpleTestCase):
    challenge_id = uuid.UUID("123e4567-e89b-42d3-a456-426614174000")
    delivery_id = uuid.UUID("123e4567-e89b-42d3-b456-426614174001")
    alternate_challenge_id = uuid.UUID("223e4567-e89b-42d3-a456-426614174000")
    alternate_delivery_id = uuid.UUID("223e4567-e89b-42d3-b456-426614174001")
    secret = bytes(range(32, 64))
    proof_key = bytes(range(32))
    rate_key = bytes(range(64, 96))
    destination_key = "owner@example.test"
    credential_body = "".join(
        (
            "Ej5FZ-ib",
            "QtOkVkJm",
            "FBdAACAh",
            "IiMkJSYn",
            "KCkqKywt",
            "Li8wMTIz",
            "NDU2Nzg5",
            "Ojs8PT4_",
        )
    )
    pending_token = f"lpv2.{credential_body}"
    reset_token = f"lpw2.{credential_body}"

    def setUp(self):
        super().setUp()
        environment = patch.dict(os.environ, {}, clear=False)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("V2_CHALLENGE_PROOF_HMAC_KEY_B64", None)
        os.environ.pop("V2_CHALLENGE_RATE_HMAC_KEY_B64", None)
        self.key_material = V2KeyMaterial(
            access_signing_key=b"a" * 32,
            refresh_hmac_key=b"r" * 32,
        )
        self.access_configuration = resolve_access_config(self.key_material)
        self.configuration = self.resolve()

    def resolve(self, **overrides):
        arguments = {
            "key_material": self.key_material,
            "access_configuration": self.access_configuration,
            "proof_key": self.proof_key,
            "rate_key": self.rate_key,
        }
        arguments.update(overrides)
        return resolve_challenge_config(**arguments)

    def assert_fixed_error(self, error_type, message, action, *sensitive_values):
        with self.assertRaises(error_type) as raised:
            action()

        exception = raised.exception
        self.assertEqual(str(exception), message)
        self.assertEqual(exception.args, (message,))
        rendered = f"{exception!s} {exception!r} {exception.args!r}"
        for sensitive_value in sensitive_values:
            sensitive_text = str(sensitive_value)
            if sensitive_text:
                self.assertNotIn(sensitive_text, rendered)

    def assert_credential_rejected(self, action, *sensitive_values):
        self.assert_fixed_error(
            ValueError,
            "Invalid v2 challenge credential.",
            action,
            *sensitive_values,
        )

    def assert_material_rejected(self, action, *sensitive_values):
        self.assert_fixed_error(
            ChallengeMaterialError,
            "Invalid v2 challenge digest material.",
            action,
            *sensitive_values,
        )

    def assert_configuration_rejected(self, action, *sensitive_values):
        self.assert_fixed_error(
            ChallengeKeyConfigurationError,
            "Invalid v2 challenge key configuration.",
            action,
            *sensitive_values,
        )

    def pending(self, **overrides):
        arguments = {
            "purpose": "signup",
            "challenge_id": self.challenge_id,
            "destination_key": self.destination_key,
            "secret": self.secret,
            "configuration": self.configuration,
        }
        arguments.update(overrides)
        return pending_context_digest(**arguments)

    def otp(self, **overrides):
        arguments = {
            "purpose": "email_change",
            "challenge_id": self.challenge_id,
            "delivery_id": self.delivery_id,
            "destination_key": self.destination_key,
            "otp": "004200",
            "configuration": self.configuration,
        }
        arguments.update(overrides)
        return otp_digest(**arguments)

    def reset(self, **overrides):
        arguments = {
            "challenge_id": self.challenge_id,
            "delivery_id": self.delivery_id,
            "destination_key": self.destination_key,
            "secret": self.secret,
            "configuration": self.configuration,
        }
        arguments.update(overrides)
        return password_reset_digest(**arguments)

    def test_pending_and_reset_credentials_have_exact_vectors_and_redacted_parts(self):
        pending = encode_v2_pending_context(self.challenge_id, self.secret)
        reset = encode_v2_password_reset_credential(self.challenge_id, self.secret)

        self.assertEqual(pending, self.pending_token)
        self.assertEqual(reset, self.reset_token)
        self.assertEqual(len(pending), 69)
        self.assertEqual(len(reset), 69)

        for decoder, value in (
            (decode_v2_pending_context, pending),
            (decode_v2_password_reset_credential, reset),
        ):
            with self.subTest(decoder=decoder.__name__):
                parts = decoder(value)
                self.assertIsInstance(parts, V2ChallengeCredentialParts)
                self.assertEqual(parts.selector, self.challenge_id)
                self.assertEqual(parts.secret, self.secret)
                self.assertEqual(
                    repr(parts),
                    "V2ChallengeCredentialParts(selector=<redacted>, secret=<redacted>)",
                )
                self.assertNotIn(str(self.challenge_id), repr(parts))
                self.assertNotIn(self.secret.hex(), repr(parts))
                with self.assertRaises(FrozenInstanceError):
                    parts.secret = b"x" * 32

    def test_credential_encoders_require_uuid4_and_exact_immutable_secret_bytes(self):
        wrong_variant = bytearray(self.challenge_id.bytes)
        wrong_variant[8] = 0x24
        invalid_selectors = (
            str(self.challenge_id),
            uuid.UUID(int=0),
            uuid.uuid1(),
            uuid.uuid5(uuid.NAMESPACE_DNS, "example.test"),
            uuid.UUID(bytes=bytes(wrong_variant)),
            None,
        )
        invalid_secrets = (
            b"s" * 31,
            b"s" * 33,
            bytearray(self.secret),
            memoryview(self.secret),
            self.secret.hex(),
            None,
        )

        for encoder in (encode_v2_pending_context, encode_v2_password_reset_credential):
            for case_index, selector in enumerate(invalid_selectors):
                with self.subTest(encoder=encoder.__name__, selector_case=case_index):
                    self.assert_credential_rejected(
                        lambda encoder=encoder, selector=selector: encoder(selector, self.secret),
                        selector,
                    )
            for case_index, secret in enumerate(invalid_secrets):
                with self.subTest(encoder=encoder.__name__, secret_case=case_index):
                    self.assert_credential_rejected(
                        lambda encoder=encoder, secret=secret: encoder(self.challenge_id, secret),
                        secret,
                    )

    def test_credential_decoders_reject_wrong_shape_prefix_alphabet_and_type(self):
        invalid_pending = (
            self.reset_token,
            self.pending_token.replace("lpv2.", "lrv2.", 1),
            self.pending_token.replace("lpv2.", "LPV2.", 1),
            self.pending_token[:-1],
            self.pending_token + "A",
            self.pending_token + "=",
            self.pending_token + " ",
            self.pending_token + "\n",
            self.pending_token[:-1] + "+",
            self.pending_token[:-1] + "/",
            self.pending_token[:-1] + "é",
            "lpv2.",
            b"lpv2.value",
            None,
            1,
        )
        invalid_reset = tuple(
            (
                self.pending_token
                if value == self.reset_token
                else value.replace("lpv2.", "lpw2.", 1) if isinstance(value, str) else value
            )
            for value in invalid_pending
        )

        for decoder, cases in (
            (decode_v2_pending_context, invalid_pending),
            (decode_v2_password_reset_credential, invalid_reset),
        ):
            for case_index, value in enumerate(cases):
                with self.subTest(decoder=decoder.__name__, case=case_index):
                    self.assert_credential_rejected(
                        lambda decoder=decoder, value=value: decoder(value),
                        value,
                    )

    def test_credential_decoders_reject_non_uuid4_and_non_rfc4122_selectors(self):
        wrong_variant = bytearray(self.challenge_id.bytes)
        wrong_variant[8] = 0x24
        invalid_selectors = (
            uuid.UUID(int=0),
            uuid.uuid1(),
            uuid.uuid5(uuid.NAMESPACE_DNS, "example.test"),
            uuid.UUID(bytes=bytes(wrong_variant)),
        )

        for decoder, prefix in (
            (decode_v2_pending_context, "lpv2."),
            (decode_v2_password_reset_credential, "lpw2."),
        ):
            for case_index, selector in enumerate(invalid_selectors):
                encoded_value = prefix + unpadded(selector.bytes + self.secret)
                with self.subTest(decoder=decoder.__name__, case=case_index):
                    self.assert_credential_rejected(
                        lambda decoder=decoder, encoded_value=encoded_value: decoder(encoded_value),
                        encoded_value,
                    )

    def test_otp_generation_uses_one_exact_bounded_draw_and_zero_padding(self):
        for value, expected in (
            (0, "000000"),
            (1, "000001"),
            (42, "000042"),
            (999999, "999999"),
        ):
            with self.subTest(value=value):
                generator = Mock(return_value=value)
                self.assertEqual(generate_v2_otp(randbelow=generator), expected)
                generator.assert_called_once_with(1_000_000)

    def test_otp_generation_rejects_invalid_or_failing_generators_with_fixed_error(self):
        invalid_values = (True, False, -1, 1_000_000, 1.0, "42", None, b"42")
        for case_index, value in enumerate(invalid_values):
            with self.subTest(case=case_index):
                generator = Mock(return_value=value)
                self.assert_fixed_error(
                    ChallengeMaterialError,
                    "Invalid v2 challenge OTP generator.",
                    lambda generator=generator: generate_v2_otp(randbelow=generator),
                    value,
                )
                generator.assert_called_once_with(1_000_000)

        sensitive = "sensitive-generator-output"
        generator = Mock(side_effect=RuntimeError(sensitive))
        self.assert_fixed_error(
            ChallengeMaterialError,
            "Invalid v2 challenge OTP generator.",
            lambda: generate_v2_otp(randbelow=generator),
            sensitive,
        )
        generator.assert_called_once_with(1_000_000)

    def test_all_five_digest_domains_match_independent_hard_coded_vectors(self):
        pending = self.pending()
        otp = self.otp()
        reset = self.reset()
        destination = destination_rate_digests(
            self.destination_key,
            configuration=self.configuration,
        )
        ipv4 = ip_rate_digests(
            4,
            32,
            ipaddress.ip_address("203.0.113.42").packed,
            configuration=self.configuration,
        )
        ipv6 = ip_rate_digests(
            6,
            64,
            ipaddress.ip_address("2001:db8:abcd:1234::").packed,
            configuration=self.configuration,
        )
        unknown = ip_rate_digests(0, 0, b"", configuration=self.configuration)

        expected = {
            "pending": "47fcd546db9398a4e6cbb011ea08eec580ff9b9298256e8e3196a4d98a701f80",
            "otp": "50c0ec77ebf23495266071e2793733441cacaf59521b5dfb3bc9504de1283bca",
            "reset": "d9d9868d13bd24242fd09d1213bbdfe1bf635bc57c41654c50c9fd675b649587",
            "destination": "51f21f02898e515d6f527a79e15ddeda124667cb348c8f180852217f341d1ede",
            "ipv4": "85ce0f94af29a4739d4bf79690035e18ea90b20c9e2957cf13dc488a3058eb95",
            "ipv6": "ba57bc4cdea9043429b5c57af64b44fd61a5de6d6da6f01ebad549c87be19760",
            "unknown": "052a3eaca42699ab0cffafe11fd468c59ee57874ac4cdb12172e83d1f37c6152",
        }
        actual = {
            "pending": pending.digest,
            "otp": otp.digest,
            "reset": reset.digest,
            "destination": destination.current.digest,
            "ipv4": ipv4.current.digest,
            "ipv6": ipv6.current.digest,
            "unknown": unknown.current.digest,
        }

        for name, digest in actual.items():
            with self.subTest(name=name):
                self.assertEqual(len(digest), hashlib.sha256().digest_size)
                self.assertEqual(digest.hex(), expected[name])

        independent = {
            "pending": framed_hmac(
                self.proof_key,
                b"ledova:v2:challenge:pending-context",
                b"signup",
                self.challenge_id.bytes,
                self.destination_key.encode("ascii"),
                self.secret,
            ),
            "otp": framed_hmac(
                self.proof_key,
                b"ledova:v2:challenge:otp",
                b"email_change",
                self.challenge_id.bytes,
                self.delivery_id.bytes,
                self.destination_key.encode("ascii"),
                b"004200",
            ),
            "reset": framed_hmac(
                self.proof_key,
                b"ledova:v2:challenge:password-reset",
                self.challenge_id.bytes,
                self.delivery_id.bytes,
                self.destination_key.encode("ascii"),
                b"password_reset",
                self.secret,
            ),
            "destination": framed_hmac(
                self.rate_key,
                b"ledova:v2:challenge:destination-rate",
                self.destination_key.encode("ascii"),
            ),
            "ipv4": framed_hmac(
                self.rate_key,
                b"ledova:v2:challenge:ip-rate",
                bytes((4,)),
                bytes((32,)),
                ipaddress.ip_address("203.0.113.42").packed,
            ),
            "ipv6": framed_hmac(
                self.rate_key,
                b"ledova:v2:challenge:ip-rate",
                bytes((6,)),
                bytes((64,)),
                ipaddress.ip_address("2001:db8:abcd:1234::").packed,
            ),
            "unknown": framed_hmac(
                self.rate_key,
                b"ledova:v2:challenge:ip-rate",
                bytes((0,)),
                bytes((0,)),
                b"",
            ),
        }
        self.assertEqual(independent, actual)

    def test_proof_digests_bind_every_field_key_and_domain(self):
        pending = self.pending(purpose="email_change").digest
        otp = self.otp().digest
        reset = self.reset().digest
        alternate_configuration = self.resolve(proof_key=b"z" * 32)

        pending_mutations = (
            self.pending(purpose="signup").digest,
            self.pending(purpose="email_change", challenge_id=self.alternate_challenge_id).digest,
            self.pending(purpose="email_change", destination_key="other@example.test").digest,
            self.pending(purpose="email_change", secret=b"x" * 32).digest,
            self.pending(purpose="email_change", configuration=alternate_configuration).digest,
        )
        otp_mutations = (
            self.otp(purpose="signup").digest,
            self.otp(challenge_id=self.alternate_challenge_id).digest,
            self.otp(delivery_id=self.alternate_delivery_id).digest,
            self.otp(destination_key="other@example.test").digest,
            self.otp(otp="004201").digest,
            self.otp(configuration=alternate_configuration).digest,
            self.otp(challenge_id=self.delivery_id, delivery_id=self.challenge_id).digest,
        )
        reset_mutations = (
            self.reset(challenge_id=self.alternate_challenge_id).digest,
            self.reset(delivery_id=self.alternate_delivery_id).digest,
            self.reset(destination_key="other@example.test").digest,
            self.reset(secret=b"x" * 32).digest,
            self.reset(configuration=alternate_configuration).digest,
            self.reset(challenge_id=self.delivery_id, delivery_id=self.challenge_id).digest,
        )

        for name, original, mutations in (
            ("pending", pending, pending_mutations),
            ("otp", otp, otp_mutations),
            ("reset", reset, reset_mutations),
        ):
            with self.subTest(name=name):
                self.assertTrue(all(value != original for value in mutations))

        self.assertEqual(len({pending, otp, reset}), 3)

    def test_digest_material_rejects_invalid_purposes_identifiers_destinations_secrets_and_otps(self):
        invalid_purposes = ("password_reset", "SIGNUP", "", None, 1, [], {})
        for case_index, purpose in enumerate(invalid_purposes):
            with self.subTest(category="purpose", case=case_index):
                self.assert_material_rejected(
                    lambda purpose=purpose: self.pending(purpose=purpose),
                    purpose,
                )

        wrong_variant = bytearray(self.challenge_id.bytes)
        wrong_variant[8] = 0x24
        invalid_identifiers = (
            str(self.challenge_id),
            uuid.UUID(int=0),
            uuid.uuid1(),
            uuid.UUID(bytes=bytes(wrong_variant)),
            None,
        )
        for case_index, identifier in enumerate(invalid_identifiers):
            with self.subTest(category="challenge", case=case_index):
                self.assert_material_rejected(
                    lambda identifier=identifier: self.pending(challenge_id=identifier),
                    identifier,
                )
            with self.subTest(category="delivery", case=case_index):
                self.assert_material_rejected(
                    lambda identifier=identifier: self.otp(delivery_id=identifier),
                    identifier,
                )

        invalid_destinations = (
            "",
            "Owner@example.test",
            " owner@example.test",
            "owner@example.test ",
            "owner\n@example.test",
            "ownér@example.test",
            "a" * 255,
            b"owner@example.test",
            None,
        )
        for case_index, destination in enumerate(invalid_destinations):
            with self.subTest(category="destination", case=case_index):
                self.assert_material_rejected(
                    lambda destination=destination: self.pending(destination_key=destination),
                    destination,
                )

        invalid_secrets = (b"s" * 31, b"s" * 33, bytearray(self.secret), self.secret.hex(), None)
        for case_index, secret in enumerate(invalid_secrets):
            with self.subTest(category="secret", case=case_index):
                self.assert_material_rejected(
                    lambda secret=secret: self.pending(secret=secret),
                    secret,
                )

        invalid_otps = (
            "00000",
            "0000000",
            " 00000",
            "00000 ",
            "+00000",
            "１２３４５６",
            "١٢٣٤٥٦",
            4200,
            b"004200",
            None,
        )
        for case_index, value in enumerate(invalid_otps):
            with self.subTest(category="otp", case=case_index):
                self.assert_material_rejected(
                    lambda value=value: self.otp(otp=value),
                    value,
                )

    def test_matchers_are_constant_time_bound_and_reject_malformed_stored_digests(self):
        pending = self.pending()
        otp = self.otp()
        reset = self.reset()

        matcher_cases = (
            (
                pending_context_matches,
                pending,
                {
                    "purpose": "signup",
                    "challenge_id": self.challenge_id,
                    "destination_key": self.destination_key,
                    "secret": self.secret,
                },
            ),
            (
                otp_matches,
                otp,
                {
                    "purpose": "email_change",
                    "challenge_id": self.challenge_id,
                    "delivery_id": self.delivery_id,
                    "destination_key": self.destination_key,
                    "otp": "004200",
                },
            ),
            (
                password_reset_matches,
                reset,
                {
                    "challenge_id": self.challenge_id,
                    "delivery_id": self.delivery_id,
                    "destination_key": self.destination_key,
                    "secret": self.secret,
                },
            ),
        )

        for matcher, keyed_digest, fields in matcher_cases:
            with self.subTest(matcher=matcher.__name__, result="match"):
                with patch(
                    "authentication.security.v2_challenges.hmac.compare_digest",
                    wraps=hmac.compare_digest,
                ) as compare:
                    self.assertTrue(
                        matcher(
                            keyed_digest.digest,
                            keyed_digest.key_id,
                            configuration=self.configuration,
                            **fields,
                        )
                    )
                    self.assertEqual(compare.call_args.args, (keyed_digest.digest, keyed_digest.digest))

            wrong_digest = b"x" * 32
            with self.subTest(matcher=matcher.__name__, result="mismatch"):
                with patch(
                    "authentication.security.v2_challenges.hmac.compare_digest",
                    wraps=hmac.compare_digest,
                ) as compare:
                    self.assertFalse(
                        matcher(
                            wrong_digest,
                            keyed_digest.key_id,
                            configuration=self.configuration,
                            **fields,
                        )
                    )
                    self.assertEqual(compare.call_args.args, (wrong_digest, keyed_digest.digest))

            with self.subTest(matcher=matcher.__name__, result="malformed"):
                with patch(
                    "authentication.security.v2_challenges.hmac.compare_digest",
                    wraps=hmac.compare_digest,
                ) as compare:
                    self.assertFalse(
                        matcher(
                            b"short",
                            keyed_digest.key_id,
                            configuration=self.configuration,
                            **fields,
                        )
                    )
                    self.assertFalse(any(call.args and call.args[0] == b"short" for call in compare.call_args_list))

    def test_unknown_malformed_and_removed_proof_key_ids_fail_closed_without_fallback(self):
        old_key = b"o" * 32
        new_key = b"n" * 32
        old_configuration = self.resolve(
            proof_key=old_key,
            current_proof_kid="proof-old",
            proof_keys={"proof-old": old_key},
        )
        overlap_configuration = self.resolve(
            proof_key=new_key,
            current_proof_kid="proof-new",
            proof_keys={"proof-new": new_key, "proof-old": old_key},
        )
        current_only_configuration = self.resolve(
            proof_key=new_key,
            current_proof_kid="proof-new",
            proof_keys={"proof-new": new_key},
        )
        old_digest = self.pending(configuration=old_configuration)

        self.assertTrue(
            pending_context_matches(
                old_digest.digest,
                old_digest.key_id,
                purpose="signup",
                challenge_id=self.challenge_id,
                destination_key=self.destination_key,
                secret=self.secret,
                configuration=overlap_configuration,
            )
        )

        for key_id in ("proof-missing", "invalid key id", old_digest.key_id):
            configuration = current_only_configuration
            with self.subTest(key_id=key_id):
                self.assert_configuration_rejected(
                    lambda key_id=key_id, configuration=configuration: pending_context_matches(
                        old_digest.digest,
                        key_id,
                        purpose="signup",
                        challenge_id=self.challenge_id,
                        destination_key=self.destination_key,
                        secret=self.secret,
                        configuration=configuration,
                    ),
                    key_id,
                    old_digest.digest.hex(),
                )

    def test_rate_digests_cover_all_accepted_keys_in_deterministic_order(self):
        old_rate_key = b"u" * 32
        current_rate_key = b"v" * 32
        first_map = {"rate-current": current_rate_key, "rate-old": old_rate_key}
        second_map = {"rate-old": old_rate_key, "rate-current": current_rate_key}
        first = self.resolve(
            rate_key=current_rate_key,
            current_rate_kid="rate-current",
            rate_keys=first_map,
        )
        second = self.resolve(
            rate_key=current_rate_key,
            current_rate_kid="rate-current",
            rate_keys=second_map,
        )

        first_destination = destination_rate_digests(self.destination_key, configuration=first)
        second_destination = destination_rate_digests(self.destination_key, configuration=second)
        first_ip = ip_rate_digests(
            4,
            32,
            ipaddress.ip_address("203.0.113.42").packed,
            configuration=first,
        )
        second_ip = ip_rate_digests(
            4,
            32,
            ipaddress.ip_address("203.0.113.42").packed,
            configuration=second,
        )

        for left, right in ((first_destination, second_destination), (first_ip, second_ip)):
            with self.subTest(domain=left.current.digest.hex()[:8]):
                self.assertIsInstance(left, ChallengeRateDigests)
                self.assertEqual(left, right)
                self.assertEqual(tuple(alias.key_id for alias in left.aliases), ("rate-current", "rate-old"))
                self.assertEqual(left.current.key_id, "rate-current")
                self.assertEqual(sum(alias == left.current for alias in left.aliases), 1)
                self.assertEqual(len({alias.digest for alias in left.aliases}), 2)
                self.assertEqual(
                    repr(left),
                    "ChallengeRateDigests(current=<redacted>, aliases=<redacted>)",
                )
                self.assertNotIn(left.current.digest.hex(), repr(left))

        first_map.clear()
        second_map["rate-injected"] = b"w" * 32
        self.assertEqual(tuple(first.rate_keys), ("rate-current", "rate-old"))
        self.assertEqual(tuple(second.rate_keys), ("rate-old", "rate-current"))
        with self.assertRaises(TypeError):
            first.rate_keys["rate-injected"] = b"w" * 32

    def test_rate_rotation_overlap_preserves_old_destination_and_ip_aliases(self):
        old_rate_key = b"u" * 32
        current_rate_key = b"v" * 32
        old_configuration = self.resolve(
            rate_key=old_rate_key,
            current_rate_kid="rate-old",
            rate_keys={"rate-old": old_rate_key},
        )
        overlap_configuration = self.resolve(
            rate_key=current_rate_key,
            current_rate_kid="rate-current",
            rate_keys={"rate-old": old_rate_key, "rate-current": current_rate_key},
        )
        current_only_configuration = self.resolve(
            rate_key=current_rate_key,
            current_rate_kid="rate-current",
            rate_keys={"rate-current": current_rate_key},
        )
        ip = ipaddress.ip_address("203.0.113.42").packed

        for digest_function, arguments in (
            (destination_rate_digests, (self.destination_key,)),
            (ip_rate_digests, (4, 32, ip)),
        ):
            with self.subTest(digest_function=digest_function.__name__):
                old = digest_function(*arguments, configuration=old_configuration).current
                overlap = digest_function(*arguments, configuration=overlap_configuration)
                current_only = digest_function(*arguments, configuration=current_only_configuration)
                self.assertIn(old, overlap.aliases)
                self.assertNotIn(old, current_only.aliases)
                self.assertEqual(overlap.current.key_id, "rate-current")

    def test_ip_rate_digest_accepts_only_three_exact_canonical_layouts(self):
        valid = (
            (0, 0, b""),
            (4, 32, ipaddress.ip_address("203.0.113.42").packed),
            (6, 64, ipaddress.ip_address("2001:db8:abcd:1234::").packed),
        )
        for address_family, prefix_length, packed_network in valid:
            with self.subTest(family=address_family):
                result = ip_rate_digests(
                    address_family,
                    prefix_length,
                    packed_network,
                    configuration=self.configuration,
                )
                self.assertEqual(result.current.key_id, INITIAL_CHALLENGE_RATE_KID)

        invalid = (
            (False, 0, b""),
            (0, False, b""),
            (0, 0, b"x"),
            (4, 24, b"\x00" * 4),
            (4, 32, b"\x00" * 3),
            (4, 32, b"\x00" * 16),
            (6, 128, b"\x00" * 16),
            (6, 64, b"\x00" * 8),
            (6, 64, ipaddress.ip_address("2001:db8:abcd:1234::1").packed),
            (1, 1, b"\x00"),
            ("4", 32, b"\x00" * 4),
            (4, 32, bytearray(b"\x00" * 4)),
        )
        for case_index, values in enumerate(invalid):
            with self.subTest(case=case_index):
                self.assert_material_rejected(
                    lambda values=values: ip_rate_digests(
                        *values,
                        configuration=self.configuration,
                    )
                )

    def test_digest_and_rate_value_objects_are_immutable_validated_and_redacted(self):
        digest = self.pending()
        rates = destination_rate_digests(self.destination_key, configuration=self.configuration)

        self.assertEqual(
            repr(digest),
            "ChallengeDigest(key_id=<redacted>, digest=<redacted>)",
        )
        self.assertNotIn(digest.key_id, repr(digest))
        self.assertNotIn(digest.digest.hex(), repr(digest))
        with self.assertRaises(FrozenInstanceError):
            digest.digest = b"x" * 32
        with self.assertRaises(FrozenInstanceError):
            rates.aliases = ()

        invalid_digests = (
            ("invalid key id", b"x" * 32),
            (INITIAL_CHALLENGE_PROOF_KID, b"x" * 31),
            (INITIAL_CHALLENGE_PROOF_KID, bytearray(b"x" * 32)),
        )
        for case_index, values in enumerate(invalid_digests):
            with self.subTest(digest_case=case_index):
                self.assert_material_rejected(lambda values=values: ChallengeDigest(*values), *values)

        valid_digest = ChallengeDigest(INITIAL_CHALLENGE_PROOF_KID, b"x" * 32)
        invalid_rates = (
            (object(), (valid_digest,)),
            (valid_digest, []),
            (valid_digest, ()),
            (valid_digest, (object(),)),
            (valid_digest, (valid_digest, valid_digest)),
        )
        for case_index, values in enumerate(invalid_rates):
            with self.subTest(rate_case=case_index):
                self.assert_material_rejected(lambda values=values: ChallengeRateDigests(*values))

    def test_challenge_configuration_is_immutable_copied_and_redacted(self):
        proof_keys = {INITIAL_CHALLENGE_PROOF_KID: self.proof_key}
        rate_keys = {INITIAL_CHALLENGE_RATE_KID: self.rate_key}
        configuration = self.resolve(proof_keys=proof_keys, rate_keys=rate_keys)

        self.assertEqual(configuration.current_proof_kid, INITIAL_CHALLENGE_PROOF_KID)
        self.assertEqual(configuration.current_rate_kid, INITIAL_CHALLENGE_RATE_KID)
        self.assertEqual(configuration.proof_key, self.proof_key)
        self.assertEqual(configuration.rate_key, self.rate_key)
        self.assertEqual(
            repr(configuration),
            "ChallengeKeyConfiguration(current_proof_kid=<redacted>, proof_key=<redacted>, "
            "proof_keys=<redacted>, current_rate_kid=<redacted>, rate_key=<redacted>, "
            "rate_keys=<redacted>)",
        )
        for sensitive in (
            configuration.current_proof_kid,
            configuration.current_rate_kid,
            configuration.proof_key.hex(),
            configuration.rate_key.hex(),
        ):
            self.assertNotIn(sensitive, repr(configuration))

        proof_keys.clear()
        rate_keys["injected"] = b"x" * 32
        self.assertEqual(tuple(configuration.proof_keys), (INITIAL_CHALLENGE_PROOF_KID,))
        self.assertEqual(tuple(configuration.rate_keys), (INITIAL_CHALLENGE_RATE_KID,))
        with self.assertRaises(TypeError):
            configuration.proof_keys["injected"] = b"x" * 32
        with self.assertRaises(TypeError):
            configuration.rate_keys["injected"] = b"x" * 32
        with self.assertRaises(FrozenInstanceError):
            configuration.proof_key = b"x" * 32

        self.assert_configuration_rejected(
            lambda: ChallengeKeyConfiguration(
                current_proof_kid=INITIAL_CHALLENGE_PROOF_KID,
                proof_key=self.proof_key,
                proof_keys={INITIAL_CHALLENGE_PROOF_KID: self.proof_key},
                current_rate_kid=INITIAL_CHALLENGE_RATE_KID,
                rate_key=self.rate_key,
                rate_keys={INITIAL_CHALLENGE_RATE_KID: self.rate_key},
            )
        )
        self.assert_configuration_rejected(lambda: replace(configuration, proof_key=b"x" * 32))

    def test_configuration_rejects_invalid_ids_keys_maps_and_current_key_mismatches(self):
        other_proof = b"p" * 32
        other_rate = b"q" * 32
        invalid_overrides = (
            {"proof_key": b"x" * 31},
            {"rate_key": b"x" * 31},
            {"proof_key": bytearray(b"x" * 32)},
            {"rate_key": memoryview(b"x" * 32)},
            {"current_proof_kid": "invalid key id"},
            {"current_rate_kid": ""},
            {"current_proof_kid": "x" * 65},
            {"current_rate_kid": "é"},
            {"proof_keys": []},
            {"rate_keys": object()},
            {"proof_keys": {}},
            {"rate_keys": {}},
            {
                "current_proof_kid": "proof-new",
                "proof_keys": {INITIAL_CHALLENGE_PROOF_KID: self.proof_key},
            },
            {
                "proof_keys": {INITIAL_CHALLENGE_PROOF_KID: other_proof},
            },
            {
                "current_rate_kid": "rate-new",
                "rate_keys": {INITIAL_CHALLENGE_RATE_KID: self.rate_key},
            },
            {
                "rate_keys": {INITIAL_CHALLENGE_RATE_KID: other_rate},
            },
            {
                "proof_keys": {
                    INITIAL_CHALLENGE_PROOF_KID: self.proof_key,
                    "proof-old": self.proof_key,
                }
            },
            {
                "rate_keys": {
                    INITIAL_CHALLENGE_RATE_KID: self.rate_key,
                    "rate-old": self.rate_key,
                }
            },
            {
                "current_rate_kid": INITIAL_CHALLENGE_PROOF_KID,
                "rate_keys": {INITIAL_CHALLENGE_PROOF_KID: self.rate_key},
            },
            {"rate_key": self.proof_key},
        )

        for case_index, overrides in enumerate(invalid_overrides):
            with self.subTest(case=case_index):
                self.assert_configuration_rejected(lambda overrides=overrides: self.resolve(**overrides))

        self.assert_configuration_rejected(
            lambda: pending_context_digest(
                purpose="signup",
                challenge_id=self.challenge_id,
                destination_key=self.destination_key,
                secret=self.secret,
                configuration=object(),
            )
        )

    def test_configuration_rejects_raw_and_encoded_reuse_across_all_key_classes(self):
        old_access_key = b"o" * 32
        rotated_access = resolve_access_config(
            self.key_material,
            verifier_keys={
                INITIAL_ACCESS_KID: self.key_material.access_signing_key,
                "ledova-v2-access-hs256-old": old_access_key,
            },
        )
        forbidden_candidates = (
            self.key_material.access_signing_key,
            self.key_material.refresh_hmac_key,
            old_access_key,
            base64.urlsafe_b64encode(self.key_material.access_signing_key),
            base64.urlsafe_b64encode(self.key_material.access_signing_key).rstrip(b"="),
            base64.urlsafe_b64encode(self.key_material.refresh_hmac_key),
            base64.urlsafe_b64encode(self.key_material.refresh_hmac_key).rstrip(b"="),
        )

        for case_index, candidate in enumerate(forbidden_candidates):
            with self.subTest(case=case_index):
                self.assert_configuration_rejected(
                    lambda candidate=candidate: self.resolve(
                        access_configuration=rotated_access,
                        proof_key=candidate,
                    ),
                    candidate.hex(),
                )

        raw_django_secret = "d" * 32
        for django_secret in (encoded(self.proof_key), unpadded(self.proof_key)):
            with self.subTest(django_form=django_secret.endswith("=")):
                with override_settings(SECRET_KEY=django_secret):
                    self.assert_configuration_rejected(
                        lambda: self.resolve(),
                        django_secret,
                        self.proof_key.hex(),
                    )

        with override_settings(SECRET_KEY=raw_django_secret):
            self.assert_configuration_rejected(
                lambda: self.resolve(proof_key=raw_django_secret.encode("ascii")),
                raw_django_secret,
            )

        encoded_rate_key = base64.urlsafe_b64encode(self.rate_key)
        self.assert_configuration_rejected(
            lambda: self.resolve(proof_key=encoded_rate_key),
            encoded_rate_key.decode("ascii"),
        )

    def test_configuration_covers_every_accepted_refresh_key(self):
        historical_refresh_key = b"h" * 32
        accepted_refresh_keys = (self.key_material.refresh_hmac_key, historical_refresh_key)

        resolved = self.resolve(accepted_refresh_keys=accepted_refresh_keys)
        self.assertIsInstance(resolved, ChallengeKeyConfiguration)

        for candidate in (
            historical_refresh_key,
            base64.urlsafe_b64encode(historical_refresh_key),
            base64.urlsafe_b64encode(historical_refresh_key).rstrip(b"="),
        ):
            with self.subTest(candidate_length=len(candidate)):
                self.assert_configuration_rejected(
                    lambda candidate=candidate: self.resolve(
                        proof_key=candidate,
                        accepted_refresh_keys=accepted_refresh_keys,
                    ),
                    candidate.hex(),
                )

        for invalid in (
            (),
            (historical_refresh_key,),
            (self.key_material.refresh_hmac_key, b"short"),
            self.key_material.refresh_hmac_key,
        ):
            with self.subTest(invalid_type=type(invalid).__name__):
                self.assert_configuration_rejected(lambda invalid=invalid: self.resolve(accepted_refresh_keys=invalid))

    def test_configuration_revalidates_supplied_access_configuration(self):
        forged = object.__new__(type(self.access_configuration))
        object.__setattr__(forged, "current_kid", self.access_configuration.current_kid)
        object.__setattr__(forged, "signing_key", b"z" * 32)
        object.__setattr__(
            forged,
            "verifier_keys",
            {self.access_configuration.current_kid: b"z" * 32},
        )

        self.assert_configuration_rejected(
            lambda: self.resolve(access_configuration=forged),
            (b"z" * 32).hex(),
        )
        self.assert_configuration_rejected(
            lambda: resolve_challenge_config(
                object(),
                self.access_configuration,
                proof_key=self.proof_key,
                rate_key=self.rate_key,
            )
        )

    def test_environment_loader_is_lazy_strict_initial_only_and_redacted(self):
        self.assertIsNotNone(self.configuration)

        valid_values = {
            "V2_CHALLENGE_PROOF_HMAC_KEY_B64": encoded(self.proof_key),
            "V2_CHALLENGE_RATE_HMAC_KEY_B64": encoded(self.rate_key),
        }
        os.environ.update(valid_values)
        loaded = load_challenge_config(self.key_material, self.access_configuration)
        self.assertEqual(loaded.current_proof_kid, INITIAL_CHALLENGE_PROOF_KID)
        self.assertEqual(loaded.current_rate_kid, INITIAL_CHALLENGE_RATE_KID)
        self.assertEqual(dict(loaded.proof_keys), {INITIAL_CHALLENGE_PROOF_KID: self.proof_key})
        self.assertEqual(dict(loaded.rate_keys), {INITIAL_CHALLENGE_RATE_KID: self.rate_key})

        for missing_name in valid_values:
            with self.subTest(missing=missing_name):
                os.environ.update(valid_values)
                os.environ.pop(missing_name)
                present_value = next(value for name, value in valid_values.items() if name != missing_name)
                self.assert_configuration_rejected(
                    lambda: load_challenge_config(self.key_material, self.access_configuration),
                    present_value,
                )

        malformed_values = (
            "not+base64/value=",
            "contains whitespace",
            "sensitive-☃-value",
            encoded(b"short"),
            encoded(self.proof_key).rstrip("="),
            f"{encoded(b'\x00' * 32)[:-2]}B=",
        )
        for case_index, value in enumerate(malformed_values):
            with self.subTest(malformed_case=case_index):
                os.environ.update(valid_values)
                os.environ["V2_CHALLENGE_PROOF_HMAC_KEY_B64"] = value
                self.assert_configuration_rejected(
                    lambda: load_challenge_config(self.key_material, self.access_configuration),
                    value,
                )

        os.environ["V2_CHALLENGE_PROOF_HMAC_KEY_B64"] = encoded(self.proof_key)
        os.environ["V2_CHALLENGE_RATE_HMAC_KEY_B64"] = encoded(self.proof_key)
        self.assert_configuration_rejected(
            lambda: load_challenge_config(self.key_material, self.access_configuration),
            encoded(self.proof_key),
        )
