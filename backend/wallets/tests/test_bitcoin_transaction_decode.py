from django.test import SimpleTestCase

from integrations.blockchain.bitcoin_transactions import (
    bitcoin_address_for_script,
    decode_bitcoin_transaction,
    script_for_bitcoin_address,
)
from wallets.tests.test_bitcoin_submission import FIXTURE


class BitcoinTransactionDecodeTest(SimpleTestCase):
    def test_a_real_core_transaction_matches_its_independent_ids_and_output_values(self):
        tx = decode_bitcoin_transaction(FIXTURE["raw_transaction"])
        self.assertEqual((tx.tx_hash, tx.witness_hash), (FIXTURE["txid"], FIXTURE["wtxid"]))
        self.assertNotEqual(tx.tx_hash, tx.witness_hash)
        self.assertEqual((tx.version, tx.lock_time), (2, 0))
        self.assertEqual((tx.inputs[0].tx_hash, tx.inputs[0].output_index), (FIXTURE["input"]["txid"], 0))
        self.assertEqual(len(tx.inputs[0].witness), 2)
        self.assertEqual(
            [(item.satoshis, item.script.hex()) for item in tx.outputs],
            [(item["satoshis"], item["script"]) for item in FIXTURE["outputs"]],
        )
        self.assertEqual(tx.raw.hex(), FIXTURE["raw_transaction"])

    def test_witness_changes_do_not_change_the_transaction_id(self):
        original = bytes.fromhex(FIXTURE["raw_transaction"])
        changed = bytearray(original)
        changed[-8] ^= 1
        observed = decode_bitcoin_transaction(bytes(changed))
        self.assertEqual(observed.tx_hash, FIXTURE["txid"])
        self.assertNotEqual(observed.witness_hash, FIXTURE["wtxid"])

    def test_legacy_serialization_hashes_all_bytes_for_both_ids(self):
        vector = FIXTURE["legacy_decoder_vector"]
        raw = bytes.fromhex(vector["raw"])
        tx = decode_bitcoin_transaction(raw)
        self.assertEqual((tx.tx_hash, tx.witness_hash), (vector["txid"], vector["wtxid"]))
        self.assertEqual(tx.inputs[0].witness, ())

    def test_malformed_encodings_are_refused_before_any_node_validation(self):
        raw = bytes.fromhex(FIXTURE["raw_transaction"])
        for value in (
            None,
            True,
            "",
            "0x" + raw.hex(),
            " " + raw.hex(),
            raw.hex() + "0",
            raw[:-1],
            raw + b"\x00",
            raw[:5] + b"\x02" + raw[6:],
            raw[:6] + b"\xfd\x01\x00" + raw[7:],
            raw[:6] + b"\xff" + b"\xff" * 8 + raw[7:],
            raw[:7] + bytes(32) + raw[39:],
            "ff" * 400001,
        ):
            with self.subTest(
                value_type=type(value).__name__, length=len(value) if isinstance(value, (str, bytes)) else 0
            ):
                with self.assertRaises(ValueError):
                    decode_bitcoin_transaction(value)

    def test_duplicate_inputs_cannot_claim_the_same_previous_output_twice(self):
        raw = bytes.fromhex(FIXTURE["raw_transaction"])
        first_input = raw[7:48]
        with self.assertRaisesRegex(ValueError, "input twice"):
            decode_bitcoin_transaction(raw[:6] + b"\x02" + first_input * 2 + raw[48:])

    def test_test_network_addresses_round_trip_to_the_expected_scripts(self):
        for address, expected in (
            (FIXTURE["sender"], FIXTURE["input"]["script"]),
            (FIXTURE["recipient"], FIXTURE["outputs"][0]["script"]),
        ):
            with self.subTest(address=address):
                script = script_for_bitcoin_address(address, "regtest")
                self.assertEqual(script.hex(), expected)
                self.assertEqual(bitcoin_address_for_script(script, "regtest"), address)
                with self.assertRaises(ValueError):
                    script_for_bitcoin_address(address, "test")
                with self.assertRaises(ValueError):
                    script_for_bitcoin_address(address, "main")
        for script in (
            bytes.fromhex("76a914" + "11" * 20 + "88ac"),
            bytes.fromhex("a914" + "11" * 20 + "87"),
            bytes.fromhex("0020" + "11" * 32),
        ):
            for network in ("test", "regtest"):
                with self.subTest(script=script.hex(), network=network):
                    self.assertEqual(
                        script_for_bitcoin_address(bitcoin_address_for_script(script, network), network), script
                    )
        with self.assertRaises(ValueError):
            bitcoin_address_for_script(bytes.fromhex("5120" + "11" * 32), "test")
