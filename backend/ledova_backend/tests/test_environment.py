from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from ledova_backend.chain_safety import parse_bitcoin_network, parse_evm_chain_id
from ledova_backend.environment import read_bool, read_choice, resolve_storage_backend


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

    def test_local_storage_works_without_debug(self):
        with patch.dict("os.environ", {"STORAGE_BACKEND": "local"}):
            self.assertEqual(resolve_storage_backend(debug=False), "local")

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
