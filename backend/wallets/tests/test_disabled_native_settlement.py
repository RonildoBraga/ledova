from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from assets.models import Asset, AssetChainDeployment
from assets.services.identity import native_asset_for_chain
from users.models import UserAccount
from wallets.models import Holding, Transaction, Wallet
from wallets.services import transaction_confirmation


class DisabledNativeSettlementTest(TestCase):
    def setUp(self):
        account = UserAccount.objects.create(account_number="NATIVE-SETTLEMENT")
        self.wallet = Wallet.objects.create(user_account=account, address="0x" + "a" * 40, chain="base")
        self.native = native_asset_for_chain("base")
        self.token = Asset.objects.create(symbol="PAY", name="Payment", asset_type="erc20_token", is_verified=True)
        self.contract = "0x" + "c" * 40
        AssetChainDeployment.objects.create(asset=self.token, chain="base", contract_address=self.contract, decimals=6)
        for target in (
            "wallets.services.transaction_confirmation.TransactionMonitoringService",
            "wallets.services.transaction_confirmation._notify_wallet_users",
        ):
            mocked = patch(target)
            mocked.start()
            self.addCleanup(mocked.stop)
        rpc = patch("wallets.services.chain.get_blockchain_client", side_effect=RuntimeError("Synthetic RPC outage"))
        rpc.start()
        self.addCleanup(rpc.stop)

    def exercise(self, event):
        configurations = ("asset_disabled", "deployment_disabled", "wrong_contract", "wrong_decimals", "missing")
        for index, configuration in enumerate(configurations):
            for token in (False, True):
                with self.subTest(configuration=configuration, token=token):
                    Asset.objects.filter(pk=self.native.pk).update(is_active=True)
                    deployment, _ = AssetChainDeployment.objects.update_or_create(
                        asset=self.native,
                        chain="base",
                        defaults={"is_active": True, "contract_address": None, "decimals": 18},
                    )
                    Holding.objects.filter(wallet=self.wallet).delete()
                    Holding.objects.create(wallet=self.wallet, asset=self.native, quantity=5)
                    Holding.objects.create(wallet=self.wallet, asset=self.token, quantity=100)
                    tx_hash = f"0x{event}-{index}-{token}"
                    transaction_confirmation.create_pending_transaction(
                        wallet=self.wallet,
                        tx_hash=tx_hash,
                        to_address="0x" + "b" * 40,
                        amount=Decimal("1"),
                        transaction_fee=Decimal("0.002"),
                        token_contract=self.contract if token else None,
                    )
                    if event == "reorged":
                        transaction_confirmation.confirm_transaction(tx_hash, wallet=self.wallet)
                    if configuration == "asset_disabled":
                        Asset.objects.filter(pk=self.native.pk).update(is_active=False)
                    elif configuration == "missing":
                        deployment.delete()
                    else:
                        fields = {
                            "deployment_disabled": {"is_active": False},
                            "wrong_contract": {"contract_address": "0x" + "d" * 40},
                            "wrong_decimals": {"decimals": 6},
                        }[configuration]
                        AssetChainDeployment.objects.filter(pk=deployment.pk).update(**fields)
                    action = {
                        "confirmed": transaction_confirmation.confirm_transaction,
                        "failed": transaction_confirmation.fail_transaction,
                        "reorged": transaction_confirmation.mark_reorged,
                    }[event]
                    for _ in range(2):
                        action(tx_hash, wallet=self.wallet)
                        tx = Transaction.objects.get(wallet=self.wallet, tx_hash=tx_hash)
                        self.assertEqual(tx.status, event)
                        expected_native = (
                            Decimal("4.998" if token else "3.998") if event == "confirmed" else Decimal("5")
                        )
                        expected_token = Decimal("99") if token and event == "confirmed" else Decimal("100")
                        self.assertEqual(
                            Holding.objects.get(wallet=self.wallet, asset=self.native).quantity, expected_native
                        )
                        self.assertEqual(
                            Holding.objects.get(wallet=self.wallet, asset=self.token).quantity, expected_token
                        )
                        self.assertIsNotNone(tx.balance_reconciliation_token)
                    if configuration == "missing":
                        self.assertFalse(AssetChainDeployment.objects.filter(asset=self.native, chain="base").exists())
                    self.assertIsNone(Asset.objects.native_for_chain("base"))

    def test_confirmation_keeps_recorded_debits_when_native_reads_are_unavailable(self):
        self.exercise("confirmed")

    def test_failure_restores_each_recorded_debit_only_once_when_native_reads_are_unavailable(self):
        self.exercise("failed")

    def test_reorg_restores_each_recorded_debit_only_once_when_native_reads_are_unavailable(self):
        self.exercise("reorged")
