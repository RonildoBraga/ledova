from decimal import Decimal
from unittest.mock import patch

from eth_account import Account
from rest_framework.test import APITransactionTestCase

from assets.models import Asset, AssetChainDeployment
from shared.db import use_operator
from shared.tests.scoped import RunsOnTheScopedConnection
from wallets.models import Holding, Transaction, WalletBalanceProjection
from wallets.tests.test_submission_families import SubmissionFamilyFixture


class TokenFamilyFixture(SubmissionFamilyFixture):
    def setUp(self):
        super().setUp()
        self.contract = Account.create().address
        with use_operator():
            self.token = Asset.objects.create(
                symbol="FUSD", name="Family token", asset_type="erc20_token", decimals=18, is_verified=True
            )
            self.deployment = AssetChainDeployment.objects.create(
                asset=self.token, chain="base", contract_address=self.contract, decimals=6
            )
            self.token_holding = Holding.objects.create(wallet=self.wallet, asset=self.token, quantity=Decimal("10"))
        self.state["token_balances"] = {self.contract.lower(): "10000000"}
        self.provider_client.get_mined_nonce.side_effect = lambda address, token_contracts=(): dict(self.state)

    def token_signed(self, **fields):
        data = bytes.fromhex("a9059cbb") + bytes(12) + bytes.fromhex(self.recipient[2:]) + (1500000).to_bytes(32, "big")
        return self.signed(to=self.contract, value=0, data=data, gas=90000, **fields)

    def token_quantity(self):
        with use_operator():
            return Holding.objects.get(pk=self.token_holding.pk).quantity


class TokenFamilyChecks(TokenFamilyFixture):
    def test_the_row_records_the_signed_fee_cap_and_ignores_a_false_declared_estimate(self):
        signed = self.token_signed()
        response = self.broadcast(signed, transaction_fee="0")
        self.assertEqual(response.status_code, 200)
        with use_operator():
            tx = Transaction.objects.get(wallet=self.wallet, tx_hash=signed.hash.to_0x_hex())
        self.assertEqual(tx.transaction_fee_estimated, Decimal("0.00018"))
        self.assertIsNone(tx.transaction_fee)
        self.assertEqual(tx.asset_id, self.token.pk)

    def test_token_bump_and_cancel_keep_one_token_principal_and_peak_native_fee(self):
        for signed in (
            self.token_signed(),
            self.token_signed(gasPrice=4 * 10**9),
            self.signed(to=self.signer.address, value=0, gasPrice=8 * 10**9),
        ):
            self.assertEqual(self.broadcast(signed).status_code, 200)
        self.assertEqual(self.token_quantity(), Decimal("8.5"))
        self.assertEqual(self.quantity(), Decimal("9.99964"))
        self.assertEqual(self.family().token_exposure, Decimal("1.5"))
        self.assertEqual(self.family().native_exposure, Decimal("0.00036"))

    def test_token_cancellation_winner_returns_token_principal_from_the_same_block_balance(self):
        original = self.token_signed()
        cancel = self.signed(to=self.signer.address, value=0, gasPrice=4 * 10**9)
        for signed in (original, cancel):
            self.assertEqual(self.broadcast(signed).status_code, 200)
        self.mined(cancel, balance="9.999916", gas_price=4 * 10**9)
        self.assertEqual(self.confirm(cancel)["status"], "confirmed")
        self.assertEqual(self.token_quantity(), Decimal("10"))
        self.assertEqual(self.quantity(), Decimal("9.999916"))
        with use_operator():
            native = Holding.objects.get(pk=self.holding.pk)
            token = Holding.objects.get(pk=self.token_holding.pk)
            self.assertEqual(native.balance_projection_id, token.balance_projection_id)
            self.assertEqual(token.balance_projection.observation["token_balances"], self.state["token_balances"])

    def test_token_balance_limits_distinct_nonce_commitments(self):
        self.state["token_balances"][self.contract.lower()] = "2000000"
        self.assertEqual(self.broadcast(self.token_signed()).status_code, 200)
        self.assertEqual(self.broadcast(self.token_signed(nonce=4)).status_code, 400)
        self.assertEqual(len(self.transactions()), 1)
        self.assertEqual(self.token_quantity(), Decimal("0.5"))

    def test_token_principal_underfunding_does_not_prevent_an_affordable_zero_extra_cancel(self):
        self.assertEqual(self.broadcast(self.token_signed()).status_code, 200)
        self.state["token_balances"][self.contract.lower()] = "0"
        self.state["balance_wei"] = str(10**14)
        self.assertEqual(
            self.broadcast(self.signed(to=self.signer.address, value=0, gasPrice=4 * 10**9)).status_code, 200
        )
        self.assertEqual(self.token_quantity(), Decimal("0"))
        self.assertEqual(self.family().token_exposure, Decimal("1.5"))

    def test_cancellation_cannot_ignore_other_token_family_commitments(self):
        self.assertEqual(self.broadcast(self.token_signed()).status_code, 200)
        self.assertEqual(self.broadcast(self.token_signed(nonce=4)).status_code, 200)
        self.state["token_balances"][self.contract.lower()] = "1000000"
        self.assertEqual(
            self.broadcast(self.signed(to=self.signer.address, value=0, gasPrice=4 * 10**9)).status_code, 400
        )
        self.assertEqual(len(self.transactions()), 2)

    def test_catalogue_mutation_during_rpc_refuses_admission_without_projection(self):
        for field in ("deployment", "asset"):
            with self.subTest(field=field):
                before = self.financial_state()

                def changed(address, token_contracts=()):
                    with use_operator():
                        if field == "deployment":
                            AssetChainDeployment.objects.filter(pk=self.deployment.pk).update(decimals=7)
                        else:
                            Asset.objects.filter(pk=self.token.pk).update(decimals=17)
                    return dict(self.state)

                self.provider_client.get_mined_nonce.side_effect = changed
                self.assertEqual(self.broadcast(self.token_signed()).status_code, 400)
                self.assertEqual(self.financial_state(), before)
                with use_operator():
                    self.assertFalse(WalletBalanceProjection.objects.filter(wallet=self.wallet).exists())
                    AssetChainDeployment.objects.filter(pk=self.deployment.pk).update(decimals=6)
                    Asset.objects.filter(pk=self.token.pk).update(decimals=18)

    def test_reconciliation_revalidates_token_scale_after_balance_rpc_and_retries_later(self):
        signed = self.token_signed()
        self.assertEqual(self.broadcast(signed).status_code, 200)
        self.mined(signed, balance="9.99982")
        self.state["token_balances"][self.contract.lower()] = "8500000"

        def changed(address, token_contracts=()):
            with use_operator():
                AssetChainDeployment.objects.filter(pk=self.deployment.pk).update(decimals=7)
            return dict(self.state)

        self.provider_client.get_mined_nonce.side_effect = changed
        self.assertEqual(self.confirm(signed)["status"], "confirmed")
        with use_operator():
            self.assertIsNotNone(
                Transaction.objects.get(pk=self.submission_for(signed).transaction_id).balance_reconciliation_token
            )
            AssetChainDeployment.objects.filter(pk=self.deployment.pk).update(decimals=6)
        self.provider_client.get_mined_nonce.side_effect = lambda address, token_contracts=(): dict(self.state)
        self.assertEqual(self.confirm(signed)["status"], "confirmed")
        self.assertEqual(self.token_quantity(), Decimal("8.5"))
        with use_operator():
            self.assertIsNone(
                Transaction.objects.get(pk=self.submission_for(signed).transaction_id).balance_reconciliation_token
            )


class TokenFamilyTest(TokenFamilyChecks, APITransactionTestCase):
    pass


class ScopedTokenFamilyTest(RunsOnTheScopedConnection, TokenFamilyChecks, APITransactionTestCase):
    pass
