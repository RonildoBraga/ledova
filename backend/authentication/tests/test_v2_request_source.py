from dataclasses import FrozenInstanceError

from django.test import RequestFactory, SimpleTestCase, override_settings

from authentication.security import (
    ChallengeRateDigests,
    V2KeyMaterial,
    V2TrustedProxyConfiguration,
    V2TrustedProxyConfigurationError,
    load_trusted_proxy_config,
    request_ip_rate_digests,
    resolve_access_config,
    resolve_challenge_config,
    resolve_trusted_proxy_config,
)

MISSING = object()


@override_settings(SECRET_KEY="django-secret-distinct-from-v2-challenge-keys")
class V2RequestSourceTest(SimpleTestCase):
    ipv4_digest = "85ce0f94af29a4739d4bf79690035e18ea90b20c9e2957cf13dc488a3058eb95"
    forwarded_ipv4_digest = "6fbf6d90fe94fa1e99048f07f994fc4f2bf114bfad205777c6b06922b31227a2"
    ipv6_digest = "ba57bc4cdea9043429b5c57af64b44fd61a5de6d6da6f01ebad549c87be19760"
    unknown_digest = "052a3eaca42699ab0cffafe11fd468c59ee57874ac4cdb12172e83d1f37c6152"
    previous_ipv4_digest = "4a966790d23723c4df34a1c2c3512cdf6cd8f71c9709283806f455dcc13eeb36"

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()
        self.key_material = V2KeyMaterial(
            access_signing_key=b"a" * 32,
            refresh_hmac_key=b"r" * 32,
        )
        self.access_configuration = resolve_access_config(self.key_material)
        self.challenge_configuration = self.resolve_challenge_configuration()

    def resolve_challenge_configuration(self, **overrides):
        arguments = {
            "key_material": self.key_material,
            "access_configuration": self.access_configuration,
            "proof_key": bytes(range(32)),
            "rate_key": bytes(range(64, 96)),
        }
        arguments.update(overrides)
        return resolve_challenge_config(**arguments)

    def request(self, *, direct=MISSING, forwarded=MISSING):
        request = self.factory.get("/")
        if direct is MISSING:
            request.META.pop("REMOTE_ADDR", None)
        else:
            request.META["REMOTE_ADDR"] = direct
        if forwarded is MISSING:
            request.META.pop("HTTP_X_FORWARDED_FOR", None)
        else:
            request.META["HTTP_X_FORWARDED_FOR"] = forwarded
        return request

    def digests(
        self,
        *,
        direct=MISSING,
        forwarded=MISSING,
        trusted=(),
        challenge_configuration=None,
    ):
        result = request_ip_rate_digests(
            self.request(direct=direct, forwarded=forwarded),
            trusted_proxy_configuration=resolve_trusted_proxy_config(trusted),
            challenge_configuration=challenge_configuration or self.challenge_configuration,
        )
        self.assertIsInstance(result, ChallengeRateDigests)
        return result

    def assert_current(self, expected, **arguments):
        result = self.digests(**arguments)
        self.assertEqual(result.current.digest.hex(), expected)
        return result

    def assert_configuration_rejected(self, action, *sensitive_values):
        with self.assertRaises(V2TrustedProxyConfigurationError) as raised:
            action()
        exception = raised.exception
        message = "Invalid v2 trusted proxy configuration."
        self.assertEqual(str(exception), message)
        self.assertEqual(exception.args, (message,))
        rendered = f"{exception!s} {exception!r} {exception.args!r}"
        for sensitive_value in sensitive_values:
            sensitive_text = str(sensitive_value)
            if sensitive_text:
                self.assertNotIn(sensitive_text, rendered)

    def test_untrusted_direct_address_ignores_every_forwarded_header_shape(self):
        forwarded_values = (
            MISSING,
            "198.51.100.7",
            "not-an-address",
            "198.51.100.é",
            " " * 2049,
            b"198.51.100.7",
            None,
        )

        for forwarded in forwarded_values:
            with self.subTest(forwarded=repr(forwarded)):
                self.assert_current(
                    self.ipv4_digest,
                    direct="203.0.113.42",
                    forwarded=forwarded,
                    trusted=("10.0.0.0/8",),
                )

    def test_trusted_proxy_validates_the_full_chain_and_selects_first_untrusted_from_right(self):
        trusted = ("10.0.0.0/8", "192.0.2.0/24")
        self.assert_current(
            self.forwarded_ipv4_digest,
            direct="10.0.0.7",
            forwarded="203.0.113.42, 198.51.100.7, 192.0.2.10",
            trusted=trusted,
        )
        self.assert_current(
            self.unknown_digest,
            direct="10.0.0.7",
            forwarded="not-an-address, 198.51.100.7, 192.0.2.10",
            trusted=trusted,
        )

    def test_ipv4_mapped_ipv6_collapses_for_source_and_trust_matching(self):
        self.assert_current(
            self.ipv4_digest,
            direct="::ffff:203.0.113.42",
        )
        self.assert_current(
            self.forwarded_ipv4_digest,
            direct="::ffff:10.0.0.7",
            forwarded="::ffff:198.51.100.7",
            trusted=("10.0.0.0/8",),
        )

    def test_ipv6_sources_share_a_hardcoded_digest_only_within_the_same_64(self):
        first = self.assert_current(
            self.ipv6_digest,
            direct="2001:db8:abcd:1234::1",
        )
        second = self.assert_current(
            self.ipv6_digest,
            direct="2001:db8:abcd:1234:ffff:ffff:ffff:ffff",
        )
        other = self.digests(direct="2001:db8:abcd:1235::1")

        self.assertEqual(first.current.digest, second.current.digest)
        self.assertNotEqual(first.current.digest, other.current.digest)

    def test_missing_and_invalid_direct_addresses_use_the_unknown_vector(self):
        invalid_values = (
            MISSING,
            None,
            "",
            " ",
            "203.0.113.42:443",
            "[2001:db8::1]",
            "[2001:db8::1]:443",
            "fe80::1%en0",
            "203.0.113.42/32",
            "203.0.113.é",
            b"203.0.113.42",
            42,
        )

        for direct in invalid_values:
            with self.subTest(direct=repr(direct)):
                self.assert_current(
                    self.unknown_digest,
                    direct=direct,
                    forwarded="198.51.100.7",
                )

    def test_trusted_proxy_requires_a_valid_bounded_forwarded_header(self):
        trusted = ("10.0.0.0/8",)
        invalid_values = (
            MISSING,
            None,
            "",
            "not-an-address",
            "198.51.100.é",
            " " * 2049,
            ",".join(["198.51.100.7"] * 11),
            b"198.51.100.7",
        )

        for forwarded in invalid_values:
            with self.subTest(forwarded=repr(forwarded)):
                self.assert_current(
                    self.unknown_digest,
                    direct="10.0.0.7",
                    forwarded=forwarded,
                    trusted=trusted,
                )

    def test_all_trusted_forwarded_chain_uses_the_unknown_vector(self):
        self.assert_current(
            self.unknown_digest,
            direct="10.0.0.7",
            forwarded="10.0.0.8, 10.0.0.9",
            trusted=("10.0.0.0/8",),
        )

    def test_forwarded_header_accepts_exact_byte_and_hop_limits(self):
        trusted = ("10.0.0.0/8",)
        exactly_2048_bytes = " " * (2048 - len("198.51.100.7")) + "198.51.100.7"
        exactly_ten_hops = ",".join(["198.51.100.7"] * 10)

        self.assertEqual(len(exactly_2048_bytes.encode("ascii")), 2048)
        self.assert_current(
            self.forwarded_ipv4_digest,
            direct="10.0.0.7",
            forwarded=exactly_2048_bytes,
            trusted=trusted,
        )
        self.assert_current(
            self.forwarded_ipv4_digest,
            direct="10.0.0.7",
            forwarded=exactly_ten_hops,
            trusted=trusted,
        )

    def test_forwarded_header_accepts_only_space_and_tab_as_optional_whitespace(self):
        trusted = ("10.0.0.0/8", "192.0.2.0/24")
        self.assert_current(
            self.forwarded_ipv4_digest,
            direct="10.0.0.7",
            forwarded=" \t198.51.100.7\t , \t192.0.2.7 \t",
            trusted=trusted,
        )

        for whitespace in ("\v", "\f", "\r", "\n", "\u00a0"):
            with self.subTest(whitespace=repr(whitespace)):
                self.assert_current(
                    self.unknown_digest,
                    direct="10.0.0.7",
                    forwarded=f"{whitespace}198.51.100.7{whitespace}",
                    trusted=trusted,
                )

    def test_forwarded_tokens_reject_ports_brackets_zones_prefixes_and_empty_values(self):
        invalid_values = (
            "198.51.100.7:443",
            "[2001:db8::1]",
            "[2001:db8::1]:443",
            "fe80::1%en0",
            "198.51.100.7/32",
            ",198.51.100.7",
            "198.51.100.7,",
            "198.51.100.7,,192.0.2.7",
            "198.51.100.7, \t,192.0.2.7",
        )

        for forwarded in invalid_values:
            with self.subTest(forwarded=forwarded):
                self.assert_current(
                    self.unknown_digest,
                    direct="10.0.0.7",
                    forwarded=forwarded,
                    trusted=("10.0.0.0/8",),
                )

    def test_configuration_is_frozen_copied_and_redacted(self):
        source = ["10.0.0.0/8", "2001:db8::/32"]
        configuration = resolve_trusted_proxy_config(source)
        source.clear()

        self.assertIsInstance(configuration, V2TrustedProxyConfiguration)
        self.assertEqual(
            repr(configuration),
            "V2TrustedProxyConfiguration(networks=<redacted>)",
        )
        self.assertNotIn("10.0.0.0/8", repr(configuration))
        self.assertNotIn("2001:db8::/32", repr(configuration))
        self.assertEqual(tuple(str(network) for network in configuration.networks), ("10.0.0.0/8", "2001:db8::/32"))
        with self.assertRaises(FrozenInstanceError):
            configuration.networks = ()

    def test_configuration_rejects_noncanonical_or_unsafe_values_with_a_fixed_error(self):
        invalid_values = (
            None,
            "10.0.0.0/8",
            {"10.0.0.0/8"},
            (b"10.0.0.0/8",),
            ("",),
            ("10.0.0.0",),
            ("10.0.0.1/8",),
            (" 10.0.0.0/8",),
            ("2001:0DB8::/32",),
            ("::ffff:0:0/96",),
            ("10.0.0.0/8", "10.0.0.0/8"),
            tuple(f"192.0.2.{index}/32" for index in range(33)),
            ("2001:db8::é/64",),
        )

        for value in invalid_values:
            with self.subTest(value=repr(value)):
                self.assert_configuration_rejected(
                    lambda value=value: resolve_trusted_proxy_config(value),
                    value,
                )

        sensitive = "198.51.100.0/24"
        self.assert_configuration_rejected(
            lambda: V2TrustedProxyConfiguration([sensitive]),
            sensitive,
        )
        self.assert_configuration_rejected(
            lambda: request_ip_rate_digests(
                self.request(direct="203.0.113.42"),
                trusted_proxy_configuration=(sensitive,),
                challenge_configuration=self.challenge_configuration,
            ),
            sensitive,
        )

    @override_settings(V2_TRUSTED_PROXY_CIDRS=("10.0.0.0/8", "192.0.2.0/24"))
    def test_load_trusted_proxy_config_uses_the_validated_setting(self):
        configuration = load_trusted_proxy_config()
        result = request_ip_rate_digests(
            self.request(
                direct="10.0.0.7",
                forwarded="198.51.100.7, 192.0.2.7",
            ),
            trusted_proxy_configuration=configuration,
            challenge_configuration=self.challenge_configuration,
        )

        self.assertEqual(result.current.digest.hex(), self.forwarded_ipv4_digest)

    @override_settings(V2_TRUSTED_PROXY_CIDRS=("private-proxy.example.test",))
    def test_load_trusted_proxy_config_redacts_invalid_setting(self):
        value = "private-proxy.example.test"
        self.assert_configuration_rejected(load_trusted_proxy_config, value)

    def test_rate_key_rotation_returns_hardcoded_current_and_previous_aliases(self):
        previous_key = bytes(range(96, 128))
        previous_configuration = self.resolve_challenge_configuration(
            current_rate_kid="rate-previous",
            rate_key=previous_key,
            rate_keys={"rate-previous": previous_key},
        )
        rotating_configuration = self.resolve_challenge_configuration(
            current_rate_kid="rate-current",
            rate_key=bytes(range(64, 96)),
            rate_keys={
                "rate-previous": previous_key,
                "rate-current": bytes(range(64, 96)),
            },
        )
        previous = self.digests(
            direct="203.0.113.42",
            challenge_configuration=previous_configuration,
        )
        rotating = self.digests(
            direct="203.0.113.42",
            challenge_configuration=rotating_configuration,
        )

        self.assertEqual(previous.current.digest.hex(), self.previous_ipv4_digest)
        self.assertEqual(rotating.current.key_id, "rate-current")
        self.assertEqual(rotating.current.digest.hex(), self.ipv4_digest)
        self.assertEqual(
            [(alias.key_id, alias.digest.hex()) for alias in rotating.aliases],
            [
                ("rate-current", self.ipv4_digest),
                ("rate-previous", self.previous_ipv4_digest),
            ],
        )
        self.assertEqual(sum(alias == rotating.current for alias in rotating.aliases), 1)
        self.assertEqual(previous.current, rotating.aliases[1])
