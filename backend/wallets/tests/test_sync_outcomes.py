from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.utils import timezone
from rest_framework.test import APITestCase

from assets.models import Asset, AssetChainDeployment
from integrations.tests.test_transfer_history_pagination import (
    CONTRACT,
    history_client,
    transfer,
)
from shared.tests.tenants import make_tenant
from wallets.models import Holding


class WalletSyncOutcomeTest(APITestCase):
    def setUp(self):
        self.tenant = make_tenant("sync-outcome")
        self.wallet = self.tenant.wallet
        self.wallet.last_synced_at = timezone.now() - timezone.timedelta(days=1)
        self.wallet.save(update_fields=["last_synced_at"])
        self.last_success = self.wallet.last_synced_at
        self.client.force_authenticate(self.tenant.user)
        provider = patch("wallets.services.sync.get_blockchain_client")
        self.addCleanup(provider.stop)
        self.provider = provider.start()
        self.provider.return_value.get_transaction_history.return_value = []
        balance = patch("wallets.services.holdings.fetch_chain_balance", return_value=Decimal("5"))
        self.addCleanup(balance.stop)
        self.balance = balance.start()

    def sync(self):
        response = self.client.post(f"/api/wallets/{self.wallet.uuid}/sync/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def assert_last_success_unchanged(self):
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.last_synced_at, self.last_success)

    def test_an_unverified_wallet_does_not_report_success_or_call_the_provider(self):
        self.wallet.verification_status = "PENDING"
        self.wallet.save(update_fields=["verification_status"])
        result = self.sync()
        self.assertFalse(result["success"])
        self.assertEqual(result["syncResult"]["status"], "skipped")
        self.assertIn("verif", result["syncResult"]["error"].lower())
        self.provider.assert_not_called()
        self.assert_last_success_unchanged()

    def test_provider_failure_reports_safe_failure_and_keeps_the_last_success(self):
        self.provider.side_effect = RuntimeError("https://provider.example.test/private-credential")
        result = self.sync()
        self.assertFalse(result["success"])
        self.assertEqual(result["syncResult"]["status"], "error")
        self.assertNotIn("private-credential", str(result))
        self.assertIn("try again", result["syncResult"]["error"].lower())
        self.assert_last_success_unchanged()

    def test_unreadable_holdings_do_not_report_a_complete_sync(self):
        self.balance.return_value = None
        self.assertTrue(Holding.objects.filter(wallet=self.wallet, asset__is_verified=True).exists())
        result = self.sync()
        self.assertFalse(result["success"])
        self.assertEqual(result["syncResult"]["status"], "error")
        self.assertIn("balance", result["syncResult"]["error"].lower())
        self.assert_last_success_unchanged()

    def test_a_complete_sync_reports_success_and_advances_the_timestamp(self):
        result = self.sync()
        self.assertTrue(result["success"])
        self.assertEqual(result["syncResult"]["status"], "success")
        self.wallet.refresh_from_db()
        self.assertGreater(self.wallet.last_synced_at, self.last_success)

    def test_an_unreadable_history_entry_does_not_stamp_a_successful_sync(self):
        self.provider.return_value.get_transaction_history.return_value = [{"tx_hash": "synthetic-invalid"}]
        result = self.sync()
        self.assertFalse(result["success"])
        self.assertEqual(result["syncResult"]["status"], "error")
        self.assert_last_success_unchanged()

    def test_a_verified_asset_first_seen_after_a_thousand_transfers_is_discovered_and_synced(self):
        asset = Asset.objects.create(symbol="LATE", name="Late token", asset_type="erc20_token", is_verified=True)
        AssetChainDeployment.objects.create(asset=asset, chain=self.wallet.chain, contract_address=CONTRACT)
        self.assertFalse(Holding.objects.filter(wallet=self.wallet, asset=asset).exists())
        reader = history_client()
        self.provider.return_value = reader
        pages = [
            {"result": {"transfers": [transfer(i) for i in range(1, 1001)], "pageKey": "newer-asset"}},
            {"result": {"transfers": [transfer(1001, CONTRACT)]}},
            {"result": {"transfers": []}},
        ]
        responses = [SimpleNamespace(raise_for_status=lambda: None, json=lambda page=page: page) for page in pages]
        with patch("integrations.blockchain.ethereum.requests.post", side_effect=responses), patch.object(
            reader, "get_transaction_receipt", return_value=None
        ):
            result = self.sync()
        self.assertTrue(result["success"], result)
        holding = Holding.objects.get(wallet=self.wallet, asset=asset)
        self.assertEqual(holding.quantity, Decimal("5"))
        self.assertIsNotNone(holding.last_synced_at)
