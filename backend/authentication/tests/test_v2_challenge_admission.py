import ipaddress
import uuid
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.db import connection
from django.test import RequestFactory, SimpleTestCase, override_settings

from authentication.security import (
    ChallengeDigest,
    ChallengeRateDigests,
    V2KeyMaterial,
    destination_rate_digests,
    ip_rate_digests,
    request_ip_rate_digests,
    resolve_access_config,
    resolve_challenge_config,
    resolve_trusted_proxy_config,
)
from authentication.services.v2_challenge_admission import (
    V2ChallengeAdmissionError,
    _admit_challenge_delivery,
    _advisory_lock_ids,
    _record_unknown_context_request_ip_suppression,
    _V2ChallengeAdmissionContext,
    _V2ChallengeAdmissionPlan,
    _validated_ip_aliases,
    _validated_rate_aliases,
    record_unknown_email_change_context_ip_suppression,
    record_unknown_signup_context_ip_suppression,
)


class EntryStateConnection:
    vendor = "postgresql"
    alias = "default"

    def __init__(self, *, in_atomic_block, autocommit):
        self.in_atomic_block = in_atomic_block
        self.autocommit = autocommit

    def get_autocommit(self):
        if isinstance(self.autocommit, Exception):
            raise self.autocommit
        return self.autocommit


@override_settings(DEBUG=False, SECRET_KEY="django-secret-distinct-from-v2-admission-keys")
class V2ChallengeAdmissionTest(SimpleTestCase):
    error = "V2 challenge service unavailable."

    def setUp(self):
        self.factory = RequestFactory()
        key_material = V2KeyMaterial(
            access_signing_key=b"a" * 32,
            refresh_hmac_key=b"r" * 32,
        )
        access_configuration = resolve_access_config(key_material)
        self.challenge_configuration = resolve_challenge_config(
            key_material,
            access_configuration,
            proof_key=b"p" * 32,
            rate_key=b"n" * 32,
            current_rate_kid="rate-2",
            rate_keys={"rate-1": b"o" * 32, "rate-2": b"n" * 32},
        )

    def assert_fixed_rejection(self, action, sensitive_value=None):
        with self.assertRaises(V2ChallengeAdmissionError) as raised:
            action()

        exception = raised.exception
        self.assertEqual(str(exception), self.error)
        self.assertEqual(repr(exception), f"V2ChallengeAdmissionError({self.error!r})")
        self.assertEqual(exception.args, (self.error,))
        self.assertIsNone(exception.__cause__)
        self.assertIsNone(exception.__context__)
        if sensitive_value is not None:
            rendered = f"{exception!s} {exception!r} {exception.args!r}"
            self.assertNotIn(sensitive_value, rendered)

    def ip_rates(self, address):
        parsed = ipaddress.ip_address(address)
        return ip_rate_digests(
            parsed.version,
            32 if parsed.version == 4 else 64,
            parsed.packed,
            configuration=self.challenge_configuration,
        )

    def destination_rates(self, destination="owner@example.test"):
        return destination_rate_digests(
            destination,
            configuration=self.challenge_configuration,
        )

    def call_admission(self, **overrides):
        arguments = {
            "purpose": "signup",
            "destination_rates": self.destination_rates(),
            "ip_rates": self.ip_rates("203.0.113.42"),
            "challenge_configuration": self.challenge_configuration,
            "using": "default",
            "post_lock_clock": lambda _cursor: datetime.now(timezone.utc),
            "lock_scope": lambda _using: None,
            "apply_admitted": lambda _scope, _context: None,
        }
        arguments.update(overrides)
        return _admit_challenge_delivery(**arguments)

    def call_public(self, request, *, trusted=(), using="default"):
        return record_unknown_signup_context_ip_suppression(
            request=request,
            trusted_proxy_configuration=resolve_trusted_proxy_config(trusted),
            challenge_configuration=self.challenge_configuration,
            using=using,
        )

    def test_public_entrypoint_derives_only_canonical_request_ip_rates(self):
        vectors = []

        direct = self.factory.post("/")
        direct.META["REMOTE_ADDR"] = "203.0.113.42"
        direct.META["HTTP_X_FORWARDED_FOR"] = "198.51.100.7"
        vectors.append((direct, (), self.ip_rates("203.0.113.42")))

        forwarded = self.factory.post("/")
        forwarded.META["REMOTE_ADDR"] = "10.0.0.7"
        forwarded.META["HTTP_X_FORWARDED_FOR"] = "198.51.100.7"
        vectors.append((forwarded, ("10.0.0.0/8",), self.ip_rates("198.51.100.7")))

        malformed = self.factory.post("/")
        malformed.META.pop("REMOTE_ADDR", None)
        unknown = ip_rate_digests(0, 0, b"", configuration=self.challenge_configuration)
        vectors.append((malformed, (), unknown))

        for request, trusted, expected in vectors:
            with self.subTest(trusted=trusted, expected=expected):
                with patch(
                    "authentication.services.v2_challenge_admission._record_unknown_context_ip_suppression"
                ) as record:
                    self.call_public(request, trusted=trusted)

                self.assertEqual(record.call_args.kwargs["ip_rates"], expected)
                self.assertIs(record.call_args.kwargs["challenge_configuration"], self.challenge_configuration)

    def test_invalid_purpose_fails_before_source_derivation_or_connection_access(self):
        sensitive_value = "private-purpose-marker"
        with (
            patch("authentication.services.v2_challenge_admission.request_ip_rate_digests") as derive,
            patch("authentication.services.v2_challenge_admission._require_unrecorded_v2_connection") as guard,
        ):
            self.assert_fixed_rejection(
                lambda: _record_unknown_context_request_ip_suppression(
                    purpose=sensitive_value,
                    request=self.factory.post("/"),
                    trusted_proxy_configuration=resolve_trusted_proxy_config(()),
                    challenge_configuration=self.challenge_configuration,
                ),
                sensitive_value,
            )

        derive.assert_not_called()
        guard.assert_not_called()

    def test_model_purpose_value_is_accepted(self):
        with patch("authentication.services.v2_challenge_admission._record_unknown_context_ip_suppression") as record:
            record_unknown_email_change_context_ip_suppression(
                request=self.factory.post("/"),
                trusted_proxy_configuration=resolve_trusted_proxy_config(()),
                challenge_configuration=self.challenge_configuration,
            )

        self.assertEqual(record.call_args.kwargs["purpose"], "email_change")

    def test_dummy_destination_precedes_source_derivation_and_is_discarded(self):
        events = []

        def derive_dummy(destination_key, *, configuration):
            events.append(("destination", destination_key))
            return destination_rate_digests(destination_key, configuration=configuration)

        def derive_ip(*args, **kwargs):
            events.append(("ip", None))
            return request_ip_rate_digests(*args, **kwargs)

        request = self.factory.post("/")
        request.META["REMOTE_ADDR"] = "203.0.113.42"
        with (
            patch(
                "authentication.services.v2_challenge_admission.destination_rate_digests",
                side_effect=derive_dummy,
            ) as dummy,
            patch(
                "authentication.services.v2_challenge_admission.request_ip_rate_digests",
                side_effect=derive_ip,
            ),
            patch("authentication.services.v2_challenge_admission._record_unknown_context_ip_suppression"),
        ):
            self.call_public(request)

        dummy.assert_called_once_with(
            "unknown-context@invalid.example",
            configuration=self.challenge_configuration,
        )
        self.assertEqual(
            events,
            [("destination", "unknown-context@invalid.example"), ("ip", None)],
        )

    def test_dummy_destination_failure_is_fixed_before_source_or_connection_access(self):
        request = self.factory.post("/")
        request.META["REMOTE_ADDR"] = "203.0.113.42"
        sensitive_value = "private-dummy-failure-marker"
        with (
            patch(
                "authentication.services.v2_challenge_admission.destination_rate_digests",
                side_effect=ValueError(sensitive_value),
            ),
            patch("authentication.services.v2_challenge_admission.request_ip_rate_digests") as derive_ip,
            patch("authentication.services.v2_challenge_admission._require_unrecorded_v2_connection") as guard,
        ):
            self.assert_fixed_rejection(lambda: self.call_public(request), sensitive_value)

        derive_ip.assert_not_called()
        guard.assert_not_called()

    def test_alias_validation_requires_the_exact_canonical_configured_set_and_writer(self):
        valid = self.ip_rates("203.0.113.42")
        old, current = valid.aliases
        extra = ChallengeDigest("rate-3", b"x" * 32)
        invalid = (
            ChallengeRateDigests(current=current, aliases=(current,)),
            ChallengeRateDigests(current=current, aliases=(old, old, current)),
            ChallengeRateDigests(current=current, aliases=valid.aliases + (extra,)),
            ChallengeRateDigests(current=old, aliases=valid.aliases),
            ChallengeRateDigests(current=current, aliases=tuple(reversed(valid.aliases))),
        )

        self.assertEqual(_validated_ip_aliases(valid, self.challenge_configuration), valid.aliases)
        for rates in invalid:
            with self.subTest(rates=rates):
                self.assert_fixed_rejection(lambda: _validated_ip_aliases(rates, self.challenge_configuration))

    def test_rate_alias_validation_applies_to_destination_and_ip_identities(self):
        valid_rates = (
            self.destination_rates(),
            self.ip_rates("203.0.113.42"),
        )

        for valid in valid_rates:
            with self.subTest(valid=valid):
                old, current = valid.aliases
                extra = ChallengeDigest("rate-3", b"x" * 32)
                invalid = (
                    ChallengeRateDigests(current=current, aliases=(current,)),
                    ChallengeRateDigests(current=current, aliases=(old, old, current)),
                    ChallengeRateDigests(current=current, aliases=valid.aliases + (extra,)),
                    ChallengeRateDigests(current=current, aliases=tuple(reversed(valid.aliases))),
                    ChallengeRateDigests(current=old, aliases=valid.aliases),
                )

                self.assertEqual(
                    _validated_rate_aliases(valid, self.challenge_configuration),
                    valid.aliases,
                )
                for rates in invalid:
                    with self.subTest(valid=valid, rates=rates):
                        self.assert_fixed_rejection(
                            lambda rates=rates: _validated_rate_aliases(
                                rates,
                                self.challenge_configuration,
                            )
                        )

    def test_advisory_lock_ids_are_signed_deduplicated_and_sorted(self):
        aliases = (
            ChallengeDigest("minimum", (-(1 << 63)).to_bytes(8, "big", signed=True) + b"a" * 24),
            ChallengeDigest("negative", (-1).to_bytes(8, "big", signed=True) + b"b" * 24),
            ChallengeDigest("zero", b"\x00" * 8 + b"c" * 24),
            ChallengeDigest("maximum", ((1 << 63) - 1).to_bytes(8, "big", signed=True) + b"d" * 24),
            ChallengeDigest("duplicate", b"\x00" * 8 + b"e" * 24),
        )

        self.assertEqual(
            _advisory_lock_ids(aliases),
            (-(1 << 63), -1, 0, (1 << 63) - 1),
        )

    def test_combined_destination_and_ip_locks_are_globally_sorted_and_deduplicated(self):
        destination_aliases = (
            ChallengeDigest("destination-minimum", (-(1 << 63)).to_bytes(8, "big", signed=True) + b"a" * 24),
            ChallengeDigest("destination-collision", b"\x00" * 8 + b"b" * 24),
        )
        ip_aliases = (
            ChallengeDigest("ip-negative", (-1).to_bytes(8, "big", signed=True) + b"c" * 24),
            ChallengeDigest("ip-collision", b"\x00" * 8 + b"d" * 24),
            ChallengeDigest("ip-maximum", ((1 << 63) - 1).to_bytes(8, "big", signed=True) + b"e" * 24),
        )

        self.assertEqual(
            _advisory_lock_ids(destination_aliases + ip_aliases),
            (-(1 << 63), -1, 0, (1 << 63) - 1),
        )

    def test_admission_context_is_immutable_and_fully_redacted(self):
        reserved_at = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
        context = _V2ChallengeAdmissionContext(
            using="private-database-alias",
            purpose="signup",
            delivery_id=uuid.UUID("123e4567-e89b-42d3-a456-426614174000"),
            reserved_at=reserved_at,
            lease_expires_at=reserved_at + timedelta(seconds=120),
            rate_key_id="private-rate-key-id",
            destination_rate_digest=b"d" * 32,
            ip_rate_digest=b"i" * 32,
        )

        self.assertEqual(repr(context), "_V2ChallengeAdmissionContext(<redacted>)")
        self.assertEqual(str(context), "_V2ChallengeAdmissionContext(<redacted>)")
        rendered = f"{context!r} {context!s}"
        for sensitive_value in (
            "private-database-alias",
            "private-rate-key-id",
            str(context.delivery_id),
            reserved_at.isoformat(),
            repr(b"d" * 32),
            repr(b"i" * 32),
        ):
            self.assertNotIn(sensitive_value, rendered)
        with self.assertRaises(FrozenInstanceError):
            context.rate_key_id = "replacement"
        self.assertFalse(hasattr(context, "__dict__"))

        plan = _V2ChallengeAdmissionPlan(
            status="suppressed",
        )
        self.assertEqual(repr(plan), "_V2ChallengeAdmissionPlan(<redacted>)")
        self.assertEqual(str(plan), "_V2ChallengeAdmissionPlan(<redacted>)")
        self.assertNotIn("suppressed", f"{plan!r} {plan!s}")
        with self.assertRaises(FrozenInstanceError):
            plan.status = "replacement"
        self.assertFalse(hasattr(plan, "__dict__"))

    def test_admission_rejects_invalid_inputs_before_connection_or_sql(self):
        destination_rates = self.destination_rates()
        old, current = destination_rates.aliases
        invalid_destination = ChallengeRateDigests(
            current=current,
            aliases=(old, old, current),
        )
        cases = (
            {"purpose": "private-invalid-purpose"},
            {"post_lock_clock": None},
            {"lock_scope": None},
            {"apply_admitted": None},
            {"destination_rates": object()},
            {"destination_rates": invalid_destination},
            {"purpose": "password_reset", "destination_rates": None},
            {"ip_rates": object()},
            {"challenge_configuration": object()},
        )

        for overrides in cases:
            with self.subTest(overrides=overrides):
                with patch("authentication.services.v2_challenge_admission._require_unrecorded_v2_connection") as guard:
                    self.assert_fixed_rejection(
                        lambda overrides=overrides: self.call_admission(**overrides),
                        "private-invalid-purpose",
                    )

                guard.assert_not_called()

    def test_admission_rejects_unsafe_connection_state_before_sql(self):
        sensitive_value = "private-entry-state-marker"
        connections = (
            EntryStateConnection(in_atomic_block=True, autocommit=True),
            EntryStateConnection(in_atomic_block=False, autocommit=False),
            EntryStateConnection(in_atomic_block=False, autocommit=1),
            EntryStateConnection(
                in_atomic_block=False,
                autocommit=ValueError(sensitive_value),
            ),
        )

        for selected in connections:
            with self.subTest(selected=selected):
                with (
                    patch(
                        "authentication.services.v2_challenge_admission._require_unrecorded_v2_connection",
                        return_value=selected,
                    ),
                    patch("authentication.services.v2_challenge_admission.transaction.atomic") as atomic,
                ):
                    self.assert_fixed_rejection(
                        self.call_admission,
                        sensitive_value,
                    )

                atomic.assert_not_called()

    def test_unsupported_database_fails_before_sql(self):
        request = self.factory.post("/")
        request.META["REMOTE_ADDR"] = "203.0.113.42"

        with patch.object(connection, "force_debug_cursor", False):
            self.assert_fixed_rejection(lambda: self.call_public(request))

    def test_query_recording_fails_before_sql(self):
        request = self.factory.post("/")
        request.META["REMOTE_ADDR"] = "203.0.113.42"

        with patch.object(connection, "force_debug_cursor", True):
            self.assert_fixed_rejection(lambda: self.call_public(request))

    def test_connection_lookup_failure_is_fixed_and_unchained(self):
        request = self.factory.post("/")
        request.META["REMOTE_ADDR"] = "203.0.113.42"
        sensitive_value = "private-database-alias-marker"

        self.assert_fixed_rejection(
            lambda: self.call_public(request, using=sensitive_value),
            sensitive_value,
        )

    def test_unsafe_or_unreadable_connection_entry_state_fails_before_sql(self):
        request = self.factory.post("/")
        request.META["REMOTE_ADDR"] = "203.0.113.42"
        sensitive_value = "private-entry-state-marker"
        connections = (
            EntryStateConnection(in_atomic_block=True, autocommit=True),
            EntryStateConnection(in_atomic_block=False, autocommit=False),
            EntryStateConnection(in_atomic_block=False, autocommit=1),
            EntryStateConnection(
                in_atomic_block=False,
                autocommit=ValueError(sensitive_value),
            ),
        )

        for selected in connections:
            with self.subTest(selected=selected):
                with patch(
                    "authentication.services.v2_challenge_admission._require_unrecorded_v2_connection",
                    return_value=selected,
                ):
                    self.assert_fixed_rejection(lambda: self.call_public(request), sensitive_value)
