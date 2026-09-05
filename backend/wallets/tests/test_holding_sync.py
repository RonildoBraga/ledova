from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from assets.models import Asset, AssetChainDeployment
from users.models import UserAccount
from wallets.models import Holding, HoldingSnapshot, Wallet
from wallets.services.holdings import sync_holding

SHARE = "0x" + "5e" * 20


class SyncHoldingTest(TestCase):
    def setUp(self):
        account = UserAccount.objects.create(account_number="HOLD-ACC")
        self.wallet = Wallet.objects.create(
            user_account=account, address="0x" + "a" * 40, chain="base", verification_status="VERIFIED"
        )
        self.share = Asset.objects.create(
            symbol="ORD", name="Acme Ordinary", asset_type="tokenized_security", decimals=0, is_verified=True
        )
        self.deployment = AssetChainDeployment.objects.create(
            asset=self.share, chain="base", contract_address=SHARE, decimals=0
        )
        self.client_mock = MagicMock()
        self.client_mock.get_token_balance.return_value = Decimal("250")

    def _chain(self, **kwargs):
        return patch("wallets.services.chain.get_blockchain_client", return_value=self.client_mock, **kwargs)

    def test_a_first_allotment_creates_the_holding_and_todays_snapshot(self):
        with self._chain():
            holding = sync_holding(self.wallet, self.share)

        self.assertIsNotNone(holding)
        self.assertEqual(holding.quantity, Decimal("250"))
        self.assertIsNotNone(holding.last_synced_at)
        snapshot = HoldingSnapshot.objects.get(holding=holding)
        self.assertEqual((snapshot.quantity, snapshot.snapshot_date), (Decimal("250"), timezone.now().date()))
        self.assertEqual(snapshot.snapshot_reason, "DAILY")
        self.assertIsNone(holding.market_value)

    def test_a_second_allotment_on_the_same_day_rewrites_one_snapshot(self):
        with self._chain():
            sync_holding(self.wallet, self.share)
            self.client_mock.get_token_balance.return_value = Decimal("400")
            holding = sync_holding(self.wallet, self.share)

        self.assertEqual(holding.quantity, Decimal("400"))
        self.assertEqual(Holding.objects.count(), 1)
        self.assertEqual(HoldingSnapshot.objects.get(holding=holding).quantity, Decimal("400"))

    def test_a_failed_read_writes_nothing_at_all(self):
        with patch("wallets.services.chain.get_blockchain_client", side_effect=RuntimeError("rpc down")):
            self.assertIsNone(sync_holding(self.wallet, self.share))

        self.assertFalse(Holding.objects.exists())
        self.assertFalse(HoldingSnapshot.objects.exists())

    def test_a_none_read_neither_creates_a_zero_holding_nor_zeroes_an_existing_one(self):
        AssetChainDeployment.objects.filter(pk=self.deployment.pk).update(contract_address=None)

        with self._chain() as factory:
            self.assertIsNone(sync_holding(self.wallet, self.share))
        self.assertFalse(Holding.objects.exists())
        factory.assert_not_called()

        existing = Holding.objects.create(wallet=self.wallet, asset=self.share, quantity=Decimal("99"))
        with self._chain():
            self.assertIsNone(sync_holding(self.wallet, self.share))

        existing.refresh_from_db()
        self.assertEqual(existing.quantity, Decimal("99"))
        self.assertFalse(HoldingSnapshot.objects.exists())

    def test_a_wallet_on_another_chain_has_no_deployment_and_is_left_alone(self):
        elsewhere = Wallet.objects.create(
            user_account=self.wallet.user_account,
            address="0x" + "b" * 40,
            chain="ethereum",
            verification_status="VERIFIED",
        )

        with self._chain():
            self.assertIsNone(sync_holding(elsewhere, self.share))

        self.assertFalse(Holding.objects.exists())
