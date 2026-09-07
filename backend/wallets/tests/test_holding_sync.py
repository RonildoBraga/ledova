from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from assets.models import Asset, AssetChainDeployment
from shared.tests.tenants import make_tenant
from tokens.services.share_token_service import ShareTokenService
from wallets.models import Holding, HoldingSnapshot, Wallet
from wallets.services.holdings import sync_holding


class SyncHoldingTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant("holdsync")
        self.wallet = self.tenant.wallet
        self.token = self.tenant.deployed_token
        self.share = Asset.objects.create(
            symbol="ORD", name="Acme Ordinary", asset_type="tokenized_security", decimals=0, is_verified=True
        )
        self.deployment = AssetChainDeployment.objects.create(
            asset=self.share, chain=self.wallet.chain, contract_address=self.token.contract_address, decimals=0
        )

    def _chain(self, balance=250, **kwargs):
        return patch.object(ShareTokenService, "get_token_balance", return_value=balance, **kwargs)

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

    def test_the_balance_comes_from_the_reader_the_register_uses(self):
        with self._chain() as reader:
            sync_holding(self.wallet, self.share)

        reader.assert_called_once_with(self.token.contract_address, self.wallet.address)

    def test_a_second_allotment_on_the_same_day_rewrites_one_snapshot(self):
        with self._chain() as reader:
            sync_holding(self.wallet, self.share)
            reader.return_value = 400
            holding = sync_holding(self.wallet, self.share)

        self.assertEqual(holding.quantity, Decimal("400"))
        self.assertEqual(Holding.objects.filter(asset=self.share).count(), 1)
        self.assertEqual(HoldingSnapshot.objects.get(holding=holding).quantity, Decimal("400"))

    def test_a_failed_read_writes_nothing_at_all(self):
        with self._chain(side_effect=RuntimeError("rpc down")):
            self.assertIsNone(sync_holding(self.wallet, self.share))

        self.assertFalse(Holding.objects.filter(asset=self.share).exists())
        self.assertFalse(HoldingSnapshot.objects.filter(holding__asset=self.share).exists())

    def test_an_address_that_names_no_share_class_is_left_alone_without_a_chain_read(self):
        AssetChainDeployment.objects.filter(pk=self.deployment.pk).update(contract_address="0x" + "5e" * 20)

        with self._chain() as reader:
            self.assertIsNone(sync_holding(self.wallet, self.share))

        reader.assert_not_called()
        self.assertFalse(Holding.objects.filter(asset=self.share).exists())

    def test_a_none_read_neither_creates_a_zero_holding_nor_zeroes_an_existing_one(self):
        AssetChainDeployment.objects.filter(pk=self.deployment.pk).update(contract_address=None)

        with self._chain() as reader:
            self.assertIsNone(sync_holding(self.wallet, self.share))
        self.assertFalse(Holding.objects.filter(asset=self.share).exists())
        reader.assert_not_called()

        existing = Holding.objects.create(wallet=self.wallet, asset=self.share, quantity=Decimal("99"))
        with self._chain():
            self.assertIsNone(sync_holding(self.wallet, self.share))

        existing.refresh_from_db()
        self.assertEqual(existing.quantity, Decimal("99"))
        self.assertFalse(HoldingSnapshot.objects.filter(holding=existing).exists())

    def test_a_wallet_on_another_chain_has_no_deployment_and_is_left_alone(self):
        elsewhere = Wallet.objects.create(
            user_account=self.wallet.user_account,
            address="0x" + "b1" * 20,
            chain="ethereum",
            verification_status="VERIFIED",
        )

        with self._chain():
            self.assertIsNone(sync_holding(elsewhere, self.share))

        self.assertFalse(Holding.objects.filter(asset=self.share).exists())
