from decimal import Decimal
from unittest.mock import patch

from rest_framework.test import APITransactionTestCase
from web3 import Web3

from assets.models import Asset, AssetChainDeployment
from shared.db import use_operator
from shared.tests.scoped import RunsOnTheScopedConnection
from wallets.models import Holding, WalletSubmission
from wallets.tests.test_submission_durability import SubmissionFixture


class SubmissionIntrinsicGasChecks(SubmissionFixture):
    def setUp(self):
        super().setUp()
        self.contract = Web3.to_checksum_address("0x" + "cc" * 20)
        self.recipient = Web3.to_checksum_address("0x" + "bb" * 20)
        self.data = (
            bytes.fromhex("a9059cbb") + bytes(12) + bytes.fromhex(self.recipient[2:]) + (1_500_000).to_bytes(32, "big")
        )
        with use_operator():
            asset = Asset.objects.create(
                symbol="IGAS", name="Intrinsic gas test token", asset_type="erc20_token", is_verified=True
            )
            AssetChainDeployment.objects.create(asset=asset, chain="base", contract_address=self.contract, decimals=6)
            Holding.objects.create(wallet=self.wallet, asset=asset, quantity=Decimal("100"))
        self.access_list = [
            {"address": self.recipient, "storageKeys": ["0x" + "00" * 32, "0x" + "00" * 32]},
            {"address": self.recipient, "storageKeys": ["0x" + "00" * 32, "0x" + "00" * 32]},
        ]

    def envelope(self, kind):
        if kind == 2:
            return {"type": 2, "maxFeePerGas": 2 * 10**9, "maxPriorityFeePerGas": 10**9}
        return {"type": 1} if kind == 1 else {}

    def reject_without_effects(self, signed):
        before = self.financial_state()
        with use_operator():
            journals = list(WalletSubmission.objects.order_by("pk").values())
        with patch("wallets.services.submissions.get_blockchain_client") as connect:
            response = self.broadcast(signed)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("intrinsic gas", response.json()["detail"].lower())
        connect.assert_not_called()
        self.assertEqual(self.financial_state(), before)
        with use_operator():
            self.assertEqual(list(WalletSubmission.objects.order_by("pk").values()), journals)

    def test_native_transfers_below_the_base_gas_requirement_cannot_reserve_funds(self):
        for kind in (None, 1, 2):
            for gas in (1, 20999):
                with self.subTest(kind=kind, gas=gas):
                    self.reject_without_effects(
                        self.signed(nonce=(kind or 0) * 100000 + gas, gas=gas, **self.envelope(kind))
                    )

    def test_access_list_gas_counts_repeated_addresses_and_storage_keys(self):
        for kind in (1, 2):
            with self.subTest(kind=kind):
                self.reject_without_effects(
                    self.signed(nonce=kind, gas=33399, accessList=self.access_list, **self.envelope(kind))
                )

    def test_erc20_calldata_and_floor_gas_are_required_for_every_supported_envelope(self):
        for kind in (None, 1, 2):
            for gas in (21595, 22489):
                with self.subTest(kind=kind, gas=gas):
                    self.reject_without_effects(
                        self.signed(
                            nonce=(kind or 0) * 100000 + gas,
                            to=self.contract,
                            value=0,
                            data=self.data,
                            gas=gas,
                            **self.envelope(kind),
                        )
                    )

    def test_erc20_access_list_gas_is_charged_in_addition_to_calldata(self):
        for kind in (1, 2):
            with self.subTest(kind=kind):
                self.reject_without_effects(
                    self.signed(
                        nonce=kind,
                        to=self.contract,
                        value=0,
                        data=self.data,
                        gas=33995,
                        accessList=self.access_list,
                        **self.envelope(kind),
                    )
                )

    def test_exact_minimum_gas_is_accepted_and_the_signed_fee_cap_is_recorded(self):
        cases = [
            ({}, 21000, {}),
            ({"type": 1}, 33400, {"accessList": self.access_list}),
            (self.envelope(2), 33400, {"accessList": self.access_list}),
            ({}, 22490, {"to": self.contract, "value": 0, "data": self.data}),
            ({"type": 1}, 33996, {"to": self.contract, "value": 0, "data": self.data, "accessList": self.access_list}),
            (
                self.envelope(2),
                33996,
                {"to": self.contract, "value": 0, "data": self.data, "accessList": self.access_list},
            ),
        ]
        for nonce, (envelope, gas, fields) in enumerate(cases):
            with self.subTest(nonce=nonce, gas=gas):
                signed = self.signed(**{"nonce": nonce, "value": 0, "gas": gas, **envelope, **fields})
                provider = self.provider(signed)
                with patch("wallets.services.submissions.get_blockchain_client", return_value=provider):
                    response = self.broadcast(signed)
                self.assertEqual(response.status_code, 200, response.content)
                provider.broadcast_transaction.assert_called_once_with(signed.raw_transaction.to_0x_hex())
                with use_operator():
                    submission = WalletSubmission.objects.select_related("transaction").get(
                        tx_hash=signed.hash.to_0x_hex()
                    )
                self.assertEqual(
                    submission.transaction.transaction_fee_estimated, Decimal(gas * 2 * 10**9) / Decimal(10**18)
                )


class SubmissionIntrinsicGasTest(SubmissionIntrinsicGasChecks, APITransactionTestCase):
    pass


class ScopedSubmissionIntrinsicGasTest(RunsOnTheScopedConnection, SubmissionIntrinsicGasChecks, APITransactionTestCase):
    pass
