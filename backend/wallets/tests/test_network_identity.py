from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.db import connection, connections
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient, APITestCase, APITransactionTestCase
from web3 import Web3

from assets.models import Asset, AssetChainDeployment
from integrations.tests.test_alchemy_webhook_network import SIGNING_KEY, post_webhook
from shared.tests.scoped import RunsOnTheScopedConnection
from shared.tests.tenants import make_tenant
from tokens.models import ShareToken, ShareTokenStatus
from wallets.exceptions import InvalidTransactionException
from wallets.models import Holding, Transaction, Wallet
from wallets.serializers.wallet import WalletSerializer
from wallets.services.signed_transfers import plan_signed_transfer
from wallets.tests.test_broadcast_transfer_guard import (
    RECIPIENT,
    SIGNER,
    erc20_transfer_data,
    sign,
)
from whitelist.exceptions import WalletNotRegisteredException
from whitelist.models import WhitelistEntry
from whitelist.services import unique_wallet_uuid_for
from whitelist.services.identity import identities_for

ADDRESS = Web3.to_checksum_address("0x" + "ab" * 20)


class WalletNetworkIdentityTest(APITestCase):
    def setUp(self):
        self.tenant = make_tenant("network-identity")
        self.client.force_authenticate(self.tenant.user)

    def register(self, chain, address=ADDRESS):
        return self.client.post(
            "/api/wallets/",
            {"userAccount": str(self.tenant.account.pk), "address": address, "chain": chain},
            format="json",
        )

    def test_one_account_can_hold_the_same_evm_address_on_two_networks(self):
        original = self.register("ethereum")
        added = self.register("base")
        self.assertEqual(original.status_code, 201, original.content)
        self.assertEqual(added.status_code, 201, added.content)
        self.assertNotEqual(original.json()["uuid"], added.json()["uuid"])
        asset = Asset.objects.create(symbol="ETH", name="Ether", asset_type="native_crypto", is_verified=True)
        for response, chain, quantity in ((original, "ethereum", 2), (added, "base", 5)):
            AssetChainDeployment.objects.create(asset=asset, chain=chain)
            Holding.objects.create(wallet_id=response.json()["uuid"], asset=asset, quantity=quantity)
            current = self.client.get(f'/api/wallets/{response.json()["uuid"]}/')
            self.assertEqual(Decimal(current.json()["nativeBalance"]), quantity)
            self.assertEqual(current.json()["chain"], chain)
            self.assertTrue(self.tenant.portfolio.wallets.filter(pk=response.json()["uuid"]).exists())

    def test_a_case_variant_is_rejected_only_on_the_same_network(self):
        first = self.register("base")
        duplicate = self.register("base", ADDRESS.lower())
        other_network = self.register("ethereum", ADDRESS.lower())
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(duplicate.status_code, 400, duplicate.content)
        self.assertIn("address", duplicate.json())
        self.assertEqual(other_network.status_code, 201, other_network.content)
        self.assertEqual(Wallet.objects.filter_by_address(ADDRESS, chain="base").count(), 1)

    def test_wallet_and_transaction_address_filters_require_a_network(self):
        for endpoint in ("wallets", "transactions"):
            with self.subTest(endpoint=endpoint):
                response = self.client.get(f"/api/{endpoint}/", {"address": ADDRESS})
                self.assertEqual(response.status_code, 400, response.content)

    def test_address_filters_return_only_the_selected_wallet_network(self):
        by_chain = {}
        for chain in ("ethereum", "base"):
            wallet = Wallet.objects.create(user_account=self.tenant.account, address=ADDRESS, chain=chain)
            transfer = Transaction.objects.create(
                wallet=wallet,
                asset=self.tenant.refs.asset,
                chain=chain,
                from_address=ADDRESS,
                to_address="0x" + "c" * 40,
                tx_hash="same-hash",
                amount=1,
            )
            by_chain[chain] = (wallet, transfer)
        base, transfer = by_chain["base"]
        for params in ({"chain": "base"}, {"wallet": str(base.pk)}):
            response = self.client.get("/api/transactions/", {"address": ADDRESS.lower(), **params})
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual([row["uuid"] for row in response.json()["results"]], [str(transfer.pk)])
        response = self.client.get("/api/wallets/", {"address": ADDRESS.lower(), "chain": "BASE"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([row["uuid"] for row in response.json()["results"]], [str(base.pk)])

    def test_bitcoin_address_filters_keep_case_significant(self):
        first = Wallet.objects.create(user_account=self.tenant.account, address="m" + "aB" * 16, chain="bitcoin")
        Wallet.objects.create(user_account=self.tenant.account, address=first.address.lower(), chain="bitcoin")
        response = self.client.get("/api/wallets/", {"address": first.address, "chain": "bitcoin"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([row["uuid"] for row in response.json()["results"]], [str(first.pk)])

    def test_registry_identity_ignores_a_wallet_on_the_other_network(self):
        base = Wallet.objects.create(user_account=self.tenant.account, address=ADDRESS, chain="base")
        other = make_tenant("other-network-owner")
        ethereum = Wallet.objects.create(user_account=other.account, address=ADDRESS, chain="ethereum")
        WhitelistEntry.objects.create(wallet=base)
        WhitelistEntry.objects.create(wallet=ethereum)
        self.assertEqual(unique_wallet_uuid_for(ADDRESS), base.pk)
        identity = identities_for([ADDRESS])[ADDRESS.lower()]
        self.assertEqual(identity.name, self.tenant.profile.full_name)
        Wallet.objects.create(user_account=other.account, address=ADDRESS, chain="base")
        with self.assertRaises(WalletNotRegisteredException):
            unique_wallet_uuid_for(ADDRESS)

    def test_register_batch_identity_matches_arbitrary_evm_address_case(self):
        mixed = "0xaB" + "ab" * 19
        self.assertNotEqual(mixed, Web3.to_checksum_address(mixed))
        base = Wallet.objects.create(user_account=self.tenant.account, address=mixed, chain="base")
        WhitelistEntry.objects.create(wallet=base)
        identity = identities_for([ADDRESS])[ADDRESS.lower()]
        self.assertEqual(identity.name, self.tenant.profile.full_name)

    def test_a_share_class_address_is_scoped_to_its_network_even_when_its_status_changes(self):
        contract = Web3.to_checksum_address("0x" + "c" * 40)
        wallet = Wallet.objects.create(user_account=self.tenant.account, address=SIGNER.address, chain="base")
        asset = Asset.objects.create(
            symbol="CROSS", name="Cross-chain token", asset_type="erc20_token", is_verified=True
        )
        AssetChainDeployment.objects.create(asset=asset, chain="base", contract_address=contract, decimals=0)
        security = ShareToken.objects.create(
            company=self.tenant.company,
            symbol="OTHER",
            name="Other network shares",
            total_supply="100",
            chain="ethereum",
            contract_address=contract,
            status=ShareTokenStatus.DEPLOYED,
        )
        signed = sign(to=contract, data=erc20_transfer_data(RECIPIENT, 1))
        self.assertEqual(plan_signed_transfer(wallet, signed).amount, Decimal("1"))
        security.chain = "base"
        security.status = ShareTokenStatus.DRAFT
        security.save(update_fields=["chain", "status"])
        with self.assertRaises(InvalidTransactionException):
            plan_signed_transfer(wallet, signed)


@skipUnless(connection.vendor == "postgresql", "Concurrent registration requires PostgreSQL")
class ConcurrentWalletRegistrationTest(TransactionTestCase):
    def setUp(self):
        self.tenant = make_tenant("concurrent-wallet")

    def test_two_requests_that_both_pass_validation_create_one_wallet(self):
        barrier = Barrier(2)
        original = WalletSerializer.validate

        def validated_together(serializer, data):
            result = original(serializer, data)
            barrier.wait(timeout=10)
            return result

        def register(address):
            try:
                client = APIClient()
                client.force_authenticate(self.tenant.user)
                response = client.post(
                    "/api/wallets/",
                    {"userAccount": str(self.tenant.account.pk), "chain": "base", "address": address},
                    format="json",
                )
                return response.status_code, response.json()
            finally:
                connections.close_all()

        with patch.object(WalletSerializer, "validate", validated_together), ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(register, (ADDRESS, ADDRESS.lower())))
        self.assertEqual(sorted(code for code, _ in outcomes), [201, 400], outcomes)
        wallet = Wallet.objects.filter_by_address(ADDRESS, chain="base").get()
        success = next(body for code, body in outcomes if code == 201)
        self.assertEqual(str(wallet.pk), success["uuid"])
        self.assertTrue(self.tenant.portfolio.wallets.filter(pk=wallet.pk).exists())


class ScopedWalletNetworkIdentityTest(RunsOnTheScopedConnection, APITransactionTestCase):
    def setUp(self):
        with self.as_an_operator_would():
            self.owner = make_tenant("scoped-wallet-owner")
            self.other = make_tenant("scoped-wallet-other")
            self.existing = Wallet.objects.create(user_account=self.owner.account, address=ADDRESS, chain="ethereum")
            self.foreign = Wallet.objects.create(user_account=self.other.account, address=ADDRESS, chain="base")
        self.signed_in_as(self.owner.user)

    def test_creating_the_other_network_uses_the_callers_account_on_the_app_connection(self):
        response = self.client.post(
            "/api/wallets/",
            {"userAccount": str(self.owner.account.pk), "address": ADDRESS, "chain": "base"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        rows = self.client.get("/api/wallets/", {"address": ADDRESS, "chain": "base"})
        self.assertEqual(rows.status_code, 200, rows.content)
        self.assertEqual([row["uuid"] for row in rows.json()["results"]], [response.json()["uuid"]])
        with self.as_an_operator_would():
            self.assertEqual(Wallet.objects.filter_by_address(ADDRESS, chain="base").count(), 2)

    def test_a_foreign_account_or_wallet_cannot_supply_the_address_scope(self):
        response = self.client.post(
            "/api/wallets/",
            {"userAccount": str(self.other.account.pk), "address": ADDRESS, "chain": "ethereum"},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        response = self.client.get("/api/transactions/", {"wallet": str(self.foreign.pk), "address": ADDRESS})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["results"], [])

    @override_settings(ALCHEMY_WEBHOOK_SIGNING_KEY=SIGNING_KEY, BLOCKCHAIN_CHAIN_ID=84532)
    def test_provider_webhooks_use_operator_visibility_and_the_reported_network(self):
        self.client.force_authenticate(user=None)
        self.no_principal_is_set()
        payload = {
            "type": "ADDRESS_ACTIVITY",
            "event": {"network": "BASE_SEPOLIA", "activity": [{"hash": "0xscoped-network", "fromAddress": ADDRESS}]},
        }
        with patch("wallets.tasks.sync_wallet.defer") as sync:
            response = post_webhook(self.client, payload)
        self.assertEqual(response.status_code, 200, response.content)
        sync.assert_called_once_with(wallet_uuid=str(self.foreign.pk))
