from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from assets.models import Asset, AssetChainDeployment
from assets.services.identity import native_asset_for_chain, quarantine_unknown_token
from assets.services.sync import AssetSyncService
from users.models import FavouriteAsset, UserAccount, UserProfile
from wallets.exceptions import InvalidTransactionException
from wallets.models import Holding, Transaction, Wallet
from wallets.services.sync import WalletSyncService
from wallets.services.transaction_confirmation import TransactionConfirmationService

User = get_user_model()
REAL_USDC = "0x" + "a0b8" + "6" * 36
FAKE_USDC = "0x" + "bad" + "0" * 37
UNKNOWN = "0x" + "c0ffee" + "1" * 34
VANITY_USDC = "0x" + "a0b866" + "f" * 34


def transfer(tx_hash, contract_address, symbol, **overrides):
    data = {
        "tx_hash": tx_hash,
        "from_address": "0x" + "e" * 40,
        "to_address": "0x" + "d" * 40,
        "amount": "25",
        "asset": symbol,
        "category": "erc20" if contract_address else "external",
        "contract_address": contract_address,
        "token_decimals": 6 if contract_address else None,
        "block_timestamp": timezone.now(),
    }
    data.update(overrides)
    return data


class UnknownTokenQuarantineTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="quarantine@example.test", password="pw-12345678")
        profile = UserProfile.objects.create(user=self.user)
        self.account = UserAccount.objects.create(account_number="QUARANTINE")
        self.account.user_profiles.add(profile)
        self.wallet = Wallet.objects.create(
            user_account=self.account, address="0x" + "d" * 40, chain="ethereum", verification_status="VERIFIED"
        )
        self.usdc = Asset.objects.create(
            symbol="USDC", name="USD Coin", asset_type="stablecoin", decimals=6, is_verified=True
        )
        AssetChainDeployment.objects.create(asset=self.usdc, chain="ethereum", contract_address=REAL_USDC, decimals=6)

    def sync(self, *transfers, wallet=None):
        client = MagicMock()
        client.get_transaction_history.return_value = list(transfers)
        with patch("wallets.services.sync.get_blockchain_client", return_value=client):
            with patch("wallets.services.sync.fetch_chain_balance", return_value=None):
                return WalletSyncService.sync_wallet(wallet or self.wallet)

    def base_wallet(self):
        return Wallet.objects.create(
            user_account=self.account, address="0x" + "b" * 40, chain="base", verification_status="VERIFIED"
        )

    def quarantined(self, symbol="MYSTERY"):
        asset = Asset.objects.create(symbol=symbol, name=symbol, asset_type="erc20_token", current_price=Decimal("1"))
        AssetChainDeployment.objects.create(asset=asset, chain="ethereum", contract_address=UNKNOWN, decimals=6)
        return asset

    def customer_sees(self, wallet=None):
        wallet = wallet or self.wallet
        self.client.force_authenticate(self.user)
        transactions = self.client.get("/api/transactions/").json()["results"]
        holdings = self.client.get(f"/api/wallets/{wallet.uuid}/holdings/").json()
        return sorted(row["txHash"] for row in transactions), sorted(row["assetSymbol"] for row in holdings)

    def deployments(self, asset):
        return list(asset.chain_deployments.values_list("chain", "contract_address"))

    def test_unknown_contract_becomes_an_unverified_asset_with_its_deployment_and_no_holding(self):
        result = self.sync(transfer("0xunknown", UNKNOWN, "MYSTERY"))

        self.assertEqual(result, {"status": "success", "transactions": 1, "snapshots": 0, "holdings": 0})
        asset = Asset.objects.get(symbol="MYSTERY")
        self.assertFalse(asset.is_verified)
        self.assertEqual((asset.asset_type, asset.decimals, asset.name), ("erc20_token", 6, "MYSTERY"))
        deployment = asset.chain_deployments.get()
        self.assertEqual((deployment.chain, deployment.contract_address, deployment.decimals), ("ethereum", UNKNOWN, 6))
        self.assertEqual(Transaction.objects.get(tx_hash="0xunknown").asset, asset)
        self.assertFalse(Holding.objects.filter(wallet=self.wallet).exists())

        self.assertEqual(self.sync(transfer("0xunknown", UNKNOWN, "MYSTERY"))["transactions"], 0)
        self.assertEqual(Asset.objects.filter(chain_deployments__contract_address=UNKNOWN).count(), 1)

    def test_a_fake_usdc_contract_never_attaches_to_the_verified_row(self):
        self.sync(transfer("0xfake", FAKE_USDC, "USDC"), transfer("0xreal", REAL_USDC, "USDC"))

        fake = Transaction.objects.get(tx_hash="0xfake").asset
        self.assertNotEqual(fake, self.usdc)
        self.assertEqual(fake.symbol, "USDC-bad000")
        self.assertFalse(fake.is_verified)
        self.assertEqual(fake.chain_deployments.get().contract_address, FAKE_USDC)
        self.assertEqual(list(self.usdc.chain_deployments.values_list("contract_address", flat=True)), [REAL_USDC])
        self.assertEqual(Transaction.objects.get(tx_hash="0xreal").asset, self.usdc)
        self.assertEqual(
            list(Holding.objects.filter(wallet=self.wallet).values_list("asset", flat=True)), [self.usdc.pk]
        )

    def test_a_fake_usdc_quarantined_before_the_seed_never_becomes_the_verified_usdc(self):
        Asset.objects.all().delete()

        fake = quarantine_unknown_token("ethereum", FAKE_USDC, "USDC", 6)
        AssetSyncService.ensure_supported_assets()

        fake.refresh_from_db()
        self.assertEqual((fake.symbol, fake.is_verified), ("USDC-bad000", False))
        self.assertEqual(
            list(fake.chain_deployments.values_list("chain", "contract_address")), [("ethereum", FAKE_USDC)]
        )
        seeded = Asset.objects.get(symbol="USDC")
        self.assertNotEqual(seeded, fake)
        self.assertTrue(seeded.is_verified)
        self.assertEqual(list(seeded.chain_deployments.values_list("chain", "contract_address")), [("ethereum", None)])

    def test_a_vanity_prefix_contract_never_lands_on_the_verified_suffixed_row(self):

        self.usdc.chain_deployments.update(contract_address=None)
        self.sync(transfer("0xreal", REAL_USDC, "USDC"))
        real = Transaction.objects.get(tx_hash="0xreal").asset
        self.assertEqual((real.symbol, real.is_verified), ("USDC-a0b866", False))
        Asset.objects.filter(pk=real.pk).update(is_verified=True)

        self.sync(transfer("0xvanity", VANITY_USDC, "USDC"), transfer("0xreal2", REAL_USDC, "USDC"))

        fake = Transaction.objects.get(tx_hash="0xvanity").asset
        self.assertNotEqual(fake, real)
        self.assertEqual((fake.symbol, fake.is_verified), ("USDC-a0b866f", False))
        self.assertEqual(self.deployments(fake), [("ethereum", VANITY_USDC)])
        self.assertEqual(self.deployments(real), [("ethereum", REAL_USDC)])
        self.assertEqual(Transaction.objects.get(tx_hash="0xreal2").asset, real)
        self.assertEqual(list(Holding.objects.filter(wallet=self.wallet).values_list("asset", flat=True)), [real.pk])
        self.assertEqual(self.customer_sees(), (["0xreal", "0xreal2"], ["USDC-a0b866"]))

    def test_a_squatter_declaring_the_suffixed_symbol_never_captures_the_real_contract(self):
        self.usdc.chain_deployments.update(contract_address=None)

        self.sync(transfer("0xsquat", FAKE_USDC, "USDC-a0b866"), transfer("0xreal", REAL_USDC, "USDC"))

        squat = Transaction.objects.get(tx_hash="0xsquat").asset
        real = Transaction.objects.get(tx_hash="0xreal").asset
        self.assertNotEqual(squat, real)
        self.assertEqual((squat.symbol, squat.is_verified), ("USDC-a0b866", False))
        self.assertEqual(self.deployments(squat), [("ethereum", FAKE_USDC)])
        self.assertEqual((real.symbol, real.is_verified), ("USDC-a0b8666", False))
        self.assertEqual(self.deployments(real), [("ethereum", REAL_USDC)])
        self.assertEqual(self.deployments(self.usdc), [("ethereum", None)])
        self.assertFalse(Holding.objects.filter(wallet=self.wallet).exists())

        Asset.objects.filter(pk=real.pk).update(is_verified=True)
        self.sync(transfer("0xsquat2", FAKE_USDC, "USDC-a0b866"), transfer("0xreal2", REAL_USDC, "USDC"))

        self.assertEqual(Transaction.objects.get(tx_hash="0xsquat2").asset, squat)
        self.assertEqual(Transaction.objects.get(tx_hash="0xreal2").asset, real)
        self.assertEqual(list(Holding.objects.filter(wallet=self.wallet).values_list("asset", flat=True)), [real.pk])
        self.assertEqual(self.customer_sees(), (["0xreal", "0xreal2"], ["USDC-a0b8666"]))

    def test_a_switched_off_deployment_refuses_the_transfer_instead_of_resolving_its_row(self):
        self.usdc.chain_deployments.update(is_active=False)
        assets_before = Asset.objects.count()

        with self.assertLogs("wallets.services.sync", level="WARNING") as logs:
            result = self.sync(transfer("0xoff", REAL_USDC, "USDC"))

        self.assertEqual(result, {"status": "success", "transactions": 0, "snapshots": 0, "holdings": 0})
        self.assertIn("switched off", "\n".join(logs.output))
        self.assertFalse(Transaction.objects.filter(tx_hash="0xoff").exists())
        self.assertFalse(Holding.objects.filter(wallet=self.wallet).exists())
        self.assertEqual(Asset.objects.count(), assets_before)
        self.assertEqual(self.deployments(self.usdc), [("ethereum", REAL_USDC)])

    def test_the_same_contract_on_another_chain_gets_its_own_row(self):
        mystery = self.quarantined()
        for ethereum_deployment_active in (True, False):
            with self.subTest(ethereum_deployment_active=ethereum_deployment_active):
                mystery.chain_deployments.update(is_active=ethereum_deployment_active)
                Asset.objects.filter(symbol="OTHER").delete()

                other = quarantine_unknown_token("base", UNKNOWN.upper(), "OTHER", 6)

                self.assertNotEqual(other, mystery)
                self.assertEqual((other.symbol, other.is_verified), ("OTHER", False))
                self.assertEqual(self.deployments(other), [("base", UNKNOWN.upper())])
                self.assertEqual(self.deployments(mystery), [("ethereum", UNKNOWN)])

    def test_a_same_address_contract_on_another_chain_never_joins_the_verified_row(self):

        base = self.base_wallet()
        for ethereum_deployment_active in (True, False):
            with self.subTest(ethereum_deployment_active=ethereum_deployment_active):
                self.usdc.chain_deployments.update(is_active=ethereum_deployment_active)
                Transaction.objects.all().delete()
                Asset.objects.exclude(pk=self.usdc.pk).delete()

                result = self.sync(transfer("0xbasefake", REAL_USDC, "USDC"), wallet=base)

                self.assertEqual(result, {"status": "success", "transactions": 1, "snapshots": 0, "holdings": 0})
                fake = Transaction.objects.get(tx_hash="0xbasefake").asset
                self.assertNotEqual(fake, self.usdc)
                self.assertEqual((fake.symbol, fake.is_verified), ("USDC-a0b866", False))
                self.assertEqual(self.deployments(fake), [("base", REAL_USDC)])
                self.assertEqual(
                    list(self.usdc.chain_deployments.values_list("chain", "contract_address", "is_active")),
                    [("ethereum", REAL_USDC, ethereum_deployment_active)],
                )
                self.assertFalse(Holding.objects.filter(wallet=base).exists())
                self.assertEqual(self.customer_sees(base), ([], []))

    def test_symbol_ownership_is_case_insensitive(self):
        self.assertEqual(quarantine_unknown_token("ethereum", FAKE_USDC, "usdc", 6).symbol, "usdc-bad000")
        self.assertEqual(quarantine_unknown_token("ethereum", UNKNOWN, "eth", 18).symbol, "eth-c0ffee")
        Asset.objects.create(symbol="Mystery", name="Mystery", asset_type="erc20_token")
        self.assertEqual(quarantine_unknown_token("ethereum", VANITY_USDC, "MYSTERY", 6).symbol, "MYSTERY-a0b866")

    def test_native_symbols_are_reserved_for_the_chain_native_coin(self):
        fake = quarantine_unknown_token("ethereum", FAKE_USDC, "POL", 18)
        self.assertEqual((fake.symbol, fake.asset_type), ("POL-bad000", "erc20_token"))

        pol = native_asset_for_chain("polygon")
        self.assertNotEqual(pol, fake)
        self.assertEqual((pol.symbol, pol.asset_type), ("POL", "native_crypto"))

        Asset.objects.filter(pk=pol.pk).update(asset_type="erc20_token")
        with self.assertRaisesRegex(ValueError, "not the native coin"):
            native_asset_for_chain("polygon")

    def test_a_native_transfer_books_against_the_chain_native_coin(self):
        eth = Asset.objects.create(symbol="ETH", name="Ether", asset_type="native_crypto", is_verified=True)
        AssetChainDeployment.objects.create(asset=eth, chain="ethereum", contract_address=None)

        assets_before = Asset.objects.count()

        self.sync(transfer("0xnative", None, "ETH", amount="1.5"))

        self.assertEqual(Transaction.objects.get(tx_hash="0xnative").asset, eth)
        self.assertEqual(Asset.objects.count(), assets_before)

    def test_quarantined_assets_are_invisible_to_customers(self):
        hidden = self.quarantined()
        FavouriteAsset.objects.create(user_account=self.account, asset=hidden)
        self.client.force_authenticate(self.user)

        listed = self.client.get("/api/assets/").json()["results"]
        self.assertEqual([row["symbol"] for row in listed], ["USDC"])
        self.assertEqual(self.client.get(f"/api/assets/{hidden.uuid}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/assets/{hidden.uuid}/snapshots/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/assets/{self.usdc.uuid}/").status_code, 200)

        favourites = self.client.get("/api/favourite-assets/").json()["results"]
        self.assertEqual(favourites, [])
        response = self.client.post(
            "/api/favourite-assets/", {"user_account": str(self.account.uuid), "asset": str(hidden.uuid)}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("asset", response.json())

    def test_a_pending_transfer_naming_an_unknown_or_unverified_token_debits_nothing(self):
        eth = Asset.objects.create(symbol="ETH", name="Ether", asset_type="native_crypto", is_verified=True)
        AssetChainDeployment.objects.create(asset=eth, chain="ethereum", contract_address=None)
        native = Holding.objects.create(wallet=self.wallet, asset=eth, quantity=Decimal("3"))
        self.quarantined()

        for contract in (FAKE_USDC, UNKNOWN):
            with self.subTest(contract=contract):
                with self.assertRaises(InvalidTransactionException):
                    TransactionConfirmationService.create_pending_transaction(
                        wallet=self.wallet,
                        tx_hash="0xpending",
                        to_address="0x" + "f" * 40,
                        amount=Decimal("1"),
                        transaction_fee=Decimal("0.01"),
                        token_contract=contract,
                    )

        native.refresh_from_db()
        self.assertEqual(native.quantity, Decimal("3"))
        self.assertFalse(Transaction.objects.filter(tx_hash="0xpending").exists())
        self.assertEqual(Holding.objects.filter(wallet=self.wallet).count(), 1)

    def test_holding_reads_and_market_values_skip_quarantined_assets(self):
        hidden = self.quarantined()
        self.usdc.current_price = Decimal("1")
        self.usdc.save(update_fields=["current_price"])
        visible = Holding.objects.create(wallet=self.wallet, asset=self.usdc, quantity=Decimal("5"))
        Holding.objects.create(wallet=self.wallet, asset=hidden, quantity=Decimal("13"))

        self.assertEqual(list(Holding.objects.active_assets_only()), [visible])
        self.assertEqual(Wallet.objects.with_market_value().get(pk=self.wallet.pk).annotated_market_value, Decimal("5"))

        self.client.force_authenticate(self.user)
        rows = self.client.get(f"/api/wallets/{self.wallet.uuid}/holdings/").json()
        self.assertEqual([row["uuid"] for row in rows], [str(visible.uuid)])
