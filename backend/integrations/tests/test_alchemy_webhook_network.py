import hashlib
import hmac
import json
from unittest.mock import call, patch

from django.test import TestCase, override_settings

from shared.tests.tenants import make_tenant
from wallets.models import Transaction, Wallet

SIGNING_KEY = "webhook-network-test"


def post_webhook(client, payload):
    body = json.dumps(payload).encode()
    signature = hmac.new(SIGNING_KEY.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        "/webhooks/alchemy/", data=body, content_type="application/json", HTTP_X_ALCHEMY_SIGNATURE=signature
    )


@override_settings(ALCHEMY_WEBHOOK_SIGNING_KEY=SIGNING_KEY, BLOCKCHAIN_CHAIN_ID=84532, ETHEREUM_CHAIN_ID=11155111)
class AlchemyWebhookNetworkTest(TestCase):
    def setUp(self):
        self.sender = make_tenant("webhook-sender")
        self.recipient = make_tenant("webhook-recipient")
        self.ethereum = Wallet.objects.create(
            user_account=self.sender.account, address=self.sender.wallet.address, chain="ethereum"
        )
        self.other_owner = Wallet.objects.create(
            user_account=self.recipient.account, address=self.sender.wallet.address.lower(), chain="base"
        )

    def activity(self, network="BASE_SEPOLIA"):
        item = {
            "fromAddress": self.sender.wallet.address.lower(),
            "toAddress": self.recipient.wallet.address.lower(),
            "hash": "0xnetwork-activity",
        }
        return {"type": "ADDRESS_ACTIVITY", "event": {"network": network, "activity": [item, item]}}

    def test_activity_routes_each_owner_and_both_sides_once_on_the_reported_network(self):
        with patch("wallets.tasks.sync_wallet.defer") as sync, patch(
            "wallets.tasks.confirm_pending_transaction.defer"
        ) as confirm:
            response = post_webhook(self.client, self.activity())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertCountEqual(
            sync.call_args_list,
            [
                call(wallet_uuid=str(wallet.pk))
                for wallet in (self.sender.wallet, self.recipient.wallet, self.other_owner)
            ],
        )
        confirm.assert_not_called()

    def test_activity_on_ethereum_does_not_route_the_base_wallet_with_the_same_address(self):
        with patch("wallets.tasks.sync_wallet.defer") as sync:
            response = post_webhook(self.client, self.activity("ETH_SEPOLIA"))
        self.assertEqual(response.status_code, 200, response.content)
        sync.assert_called_once_with(wallet_uuid=str(self.ethereum.pk))

    def test_pending_receipts_are_queued_only_for_the_matching_wallet_network(self):
        for wallet in (self.sender.wallet, self.ethereum):
            Transaction.objects.create(
                wallet=wallet,
                chain=wallet.chain,
                asset=self.sender.refs.asset,
                tx_hash="0xnetwork-activity",
                from_address=wallet.address,
                to_address=self.recipient.wallet.address,
                amount=1,
                status="pending",
            )
        with patch("wallets.tasks.confirm_pending_transaction.defer") as confirm:
            with patch("wallets.tasks.sync_wallet.defer"):
                response = post_webhook(self.client, self.activity())
        self.assertEqual(response.status_code, 200, response.content)
        confirm.assert_called_once_with(
            tx_hash="0xnetwork-activity", wallet_uuid=str(self.sender.wallet.pk), principal_id=None
        )

    def test_mined_contract_creation_uses_the_explicit_network_with_no_recipient(self):
        payload = {
            "type": "MINED_TRANSACTION",
            "event": {
                "network": "ETH_SEPOLIA",
                "transaction": {"hash": "0xcreation", "from": self.ethereum.address.lower(), "to": None},
            },
        }
        with patch("wallets.tasks.sync_wallet.defer") as sync:
            response = post_webhook(self.client, payload)
        self.assertEqual(response.status_code, 200, response.content)
        sync.assert_called_once_with(wallet_uuid=str(self.ethereum.pk))

    def test_unknown_or_missing_networks_never_queue_work(self):
        for network in (None, "", "BASE_MAINNET", "ETH_MAINNET", "MATIC_MUMBAI", {}):
            with self.subTest(network=network), patch("wallets.tasks.sync_wallet.defer") as sync, patch(
                "wallets.tasks.confirm_pending_transaction.defer"
            ) as confirm:
                response = post_webhook(self.client, self.activity(network))
                self.assertEqual(response.status_code, 400, response.content)
                sync.assert_not_called()
                confirm.assert_not_called()

    @override_settings(BLOCKCHAIN_CHAIN_ID=31337, ETHEREUM_CHAIN_ID=1337)
    def test_testnet_events_are_refused_when_the_wallet_network_uses_a_local_chain(self):
        for network in ("BASE_SEPOLIA", "ETH_SEPOLIA"):
            with self.subTest(network=network), patch("wallets.tasks.sync_wallet.defer") as sync:
                response = post_webhook(self.client, self.activity(network))
                self.assertEqual(response.status_code, 400, response.content)
                sync.assert_not_called()
