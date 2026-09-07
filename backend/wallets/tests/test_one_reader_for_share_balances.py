from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from assets.models import Asset, AssetChainDeployment
from shared.tests.tenants import make_tenant
from tokens.services.register import token_register
from tokens.services.share_token_service import ShareTokenService
from wallets.models import Holding
from wallets.services.sync import WalletSyncService

CACHED = Decimal("12000")
ON_CHAIN = 11000


class TheCacheAndTheRegisterReadOneChainTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant("onereader")
        self.wallet = self.tenant.wallet
        self.token = self.tenant.deployed_token
        self.asset = Asset.objects.create(
            symbol="ORD", name="Acme Ordinary", asset_type="tokenized_security", decimals=0, is_verified=True
        )
        AssetChainDeployment.objects.create(
            asset=self.asset, chain=self.wallet.chain, contract_address=self.token.contract_address, decimals=0
        )
        self.holding = Holding.objects.create(wallet=self.wallet, asset=self.asset, quantity=CACHED)

    def _chain(self, balance=ON_CHAIN):
        self.addCleanup(patch.stopall)
        patch("tokens.services.share_token_service.get_base_chain_client").start()
        patch.object(ShareTokenService, "deployment_block", return_value=1).start()
        patch.object(ShareTokenService, "transfer_participants", return_value={self.wallet.address}).start()
        patch.object(ShareTokenService, "share_supply", return_value=(0, balance)).start()
        return patch.object(ShareTokenService, "get_token_balance", return_value=balance).start()

    def test_a_transfer_the_platform_did_not_make_is_closed_by_the_next_sync(self):
        self._chain()

        WalletSyncService._sync_holdings_from_blockchain(self.wallet)

        self.holding.refresh_from_db()
        self.assertEqual(self.holding.quantity, Decimal(ON_CHAIN))

    def test_a_decimals_column_the_contract_never_agreed_to_no_longer_divides_the_holding(self):
        AssetChainDeployment.objects.filter(asset=self.asset).update(decimals=2)
        self._chain()

        WalletSyncService._sync_holdings_from_blockchain(self.wallet)

        self.holding.refresh_from_db()
        self.assertEqual(self.holding.quantity, Decimal(ON_CHAIN))

    def test_the_register_and_the_holding_state_the_same_number_after_that_sync(self):
        self._chain()

        WalletSyncService._sync_holdings_from_blockchain(self.wallet)
        rows, _ = token_register(self.token)

        self.holding.refresh_from_db()
        listed = {row["address"].lower(): int(row["balance"]) for row in rows}
        self.assertEqual(listed[self.wallet.address.lower()], int(self.holding.quantity))

    def test_reading_the_register_leaves_the_cache_exactly_where_it_was(self):
        self._chain()

        token_register(self.token)

        self.holding.refresh_from_db()
        self.assertEqual(self.holding.quantity, CACHED)
        self.assertIsNone(self.holding.last_synced_at)

    def test_both_surfaces_call_the_same_reader(self):
        reader = self._chain()

        WalletSyncService._sync_holdings_from_blockchain(self.wallet)
        token_register(self.token)

        self.assertEqual(
            [call.args for call in reader.call_args_list],
            [(self.token.contract_address, self.wallet.address)] * 2,
        )


class TheWalletDoesNotClaimAFreshnessItDoesNotHaveTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant("freshness")
        self.wallet = self.tenant.wallet
        self.token = self.tenant.deployed_token
        self.asset = Asset.objects.create(
            symbol="ORD", name="Acme Ordinary", asset_type="tokenized_security", decimals=0, is_verified=True
        )
        AssetChainDeployment.objects.create(
            asset=self.asset, chain=self.wallet.chain, contract_address=self.token.contract_address, decimals=0
        )
        Holding.objects.create(wallet=self.wallet, asset=self.asset, quantity=CACHED)
        self.addCleanup(patch.stopall)
        patch("tokens.services.share_token_service.get_base_chain_client").start()
        client = patch("wallets.services.sync.get_blockchain_client").start()
        client.return_value.get_transaction_history.return_value = []
        patch("wallets.services.chain.get_blockchain_client").start().return_value.get_token_balance.return_value = None

    def test_a_holding_the_chain_would_not_answer_leaves_the_stamp_where_it_was(self):
        patch.object(ShareTokenService, "get_token_balance", side_effect=RuntimeError("rpc down")).start()

        with self.assertLogs("wallets.services.sync", level="WARNING") as logs:
            WalletSyncService.sync_wallet(self.wallet)

        self.wallet.refresh_from_db()
        self.assertIsNone(self.wallet.last_synced_at)
        self.assertIn("last_synced_at stays where it was", "\n".join(logs.output))

    def test_a_sync_that_read_every_holding_does_stamp_it(self):
        patch.object(ShareTokenService, "get_token_balance", return_value=ON_CHAIN).start()
        Holding.objects.filter(wallet=self.wallet).exclude(asset=self.asset).delete()

        WalletSyncService.sync_wallet(self.wallet)

        self.wallet.refresh_from_db()
        self.assertIsNotNone(self.wallet.last_synced_at)
