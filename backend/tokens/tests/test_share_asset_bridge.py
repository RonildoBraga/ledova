from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from web3 import Web3

from assets.models import Asset, AssetChainDeployment, AssetType
from assets.services.identity import quarantine_unknown_token
from shared.tests.tenants import make_tenant
from tokens.models import (
    IssuanceStatus,
    RequestStatus,
    ShareIssuance,
    ShareIssuanceRequest,
)
from tokens.services import ShareTokenService
from tokens.services.share_token_service import SHARE_ASSET_CHAIN
from wallets.models import Holding
from whitelist.models import WhitelistEntry, WhitelistStatus

CHAIN_CLIENT = "tokens.services.share_token_service.get_base_chain_client"
SWAP = "tokens.services.share_token_service.ShareTokenService._approve_for_swap"
WHITELISTED = "tokens.services.share_token_service.ShareTokenService.is_recipient_whitelisted"
SUPPLY = "tokens.services.share_token_service.ShareTokenService.share_supply"
CREATED = "0x" + "c0ffee" + "0" * 34
ELSEWHERE = "0x" + "dead" + "0" * 36
SIGNER = "0x" + "e" * 40
RECEIPT = {"blockNumber": 9, "blockHash": bytes.fromhex("ab" * 32), "gasUsed": 1_000_000}


def factory(existing):
    contract = Mock()
    contract.functions.getTokenByIdentifier.return_value.call.return_value = existing
    return contract


@override_settings(SHARE_TOKEN_FACTORY_ADDRESS="0x" + "f" * 40, BLOCKCHAIN_OPERATOR_KEY="0xkey")
class ShareAssetBridgeTest(TestCase):
    def setUp(self):
        self.chain = patch(CHAIN_CLIENT).start().return_value
        self.chain.load_contract.return_value.functions.authorizedShares.return_value.call.return_value = 1000
        patch(SWAP).start()
        self.addCleanup(patch.stopall)
        self.tenant = make_tenant("owner")
        self.token = self.tenant.token
        self.token.mark_deploying()

    def _service(self, existing=CREATED):
        service = ShareTokenService()
        service._factory_contract = factory(existing)
        return service

    def _shares(self):
        return Asset.objects.filter(asset_type=AssetType.TOKENIZED_SECURITY.value).exclude(symbol__startswith="TENANT")

    def test_deploying_writes_a_verified_asset_at_the_address_the_factory_reported(self):
        result = self._service().deploy_token(self.token)

        self.assertEqual((result["contract_address"], result["adopted"]), (CREATED, True))
        asset = self._shares().get()
        self.assertEqual((asset.symbol, asset.decimals, asset.is_verified), ("DRF", 0, True))
        self.assertEqual(asset.name, f"{self.tenant.company.name} {self.token.name}")
        self.assertIsNone(asset.current_price)
        deployment = asset.chain_deployments.get()
        self.assertEqual((deployment.chain, deployment.contract_address), (SHARE_ASSET_CHAIN, CREATED))

    def test_running_the_deploy_path_twice_leaves_exactly_one_asset_and_one_deployment(self):
        self._service().deploy_token(self.token)
        self.token.refresh_from_db()
        self._service().deploy_token(self.token)

        self.assertEqual(self._shares().count(), 1)
        self.assertEqual(AssetChainDeployment.objects.filter(contract_address=CREATED).count(), 1)

    def test_the_five_minute_sweep_resolving_the_same_deployment_writes_no_second_asset(self):
        self._service().deploy_token(self.token)
        self.token.refresh_from_db()

        self.assertEqual(self._service().resolve_pending_deployment(self.token), CREATED)

        self.assertEqual(self._shares().count(), 1)
        self.assertEqual(AssetChainDeployment.objects.filter(contract_address=CREATED).count(), 1)

    def test_an_address_the_factory_does_not_hold_leaves_the_quarantined_row_unverified(self):
        quarantined = quarantine_unknown_token(
            chain=SHARE_ASSET_CHAIN, contract_address=ELSEWHERE, symbol="DRF", decimals=18
        )

        with self.assertLogs("tokens.services.share_token_service", level="WARNING") as logs:
            self._service(existing=CREATED)._finish_deployment(self.token, ELSEWHERE)

        self.assertIn("is not the address the factory holds", "\n".join(logs.output))
        quarantined.refresh_from_db()
        self.assertFalse(quarantined.is_verified)
        self.assertEqual((quarantined.asset_type, quarantined.decimals), ("erc20_token", 18))
        self.assertEqual(self._shares().count(), 0)
        self.token.refresh_from_db()
        self.assertEqual(self.token.contract_address, ELSEWHERE)

    def test_two_companies_sharing_a_symbol_get_two_distinct_assets(self):
        self._service().deploy_token(self.token)
        other = make_tenant("rival")
        rival_token = other.token
        rival_token.mark_deploying()

        self._service(existing=ELSEWHERE).deploy_token(rival_token)

        symbols = sorted(self._shares().values_list("symbol", flat=True))
        self.assertEqual(symbols, ["DRF", f"DRF.{other.company.acn}"])
        self.assertEqual(
            Asset.objects.get(symbol=f"DRF.{other.company.acn}").chain_deployments.get().contract_address, ELSEWHERE
        )


@override_settings(BLOCKCHAIN_OPERATOR_KEY="0xkey")
class IssuanceSeedsTheHoldingTest(TestCase):
    def setUp(self):
        self.chain = patch(CHAIN_CLIENT).start().return_value
        self.chain.is_valid_address.return_value = True
        self.chain.to_checksum_address.side_effect = Web3.to_checksum_address
        self.chain.get_address_from_private_key.return_value = SIGNER
        self.chain.load_contract.return_value.functions.paused.return_value.call.return_value = False
        self.chain.send_transaction.return_value = ("0xmint", None)
        self.chain.wait_for_receipt.return_value = RECEIPT
        self.chain.get_transaction_receipt.return_value = None
        patch(WHITELISTED, return_value=True).start()
        patch(SUPPLY, return_value=(1000, 0)).start()
        self.addCleanup(patch.stopall)
        self.tenant = make_tenant("owner")
        self.token = self.tenant.deployed_token
        self.wallet = self.tenant.wallet
        self.asset = Asset.objects.create(
            symbol="DEP",
            name="Owner shares",
            asset_type=AssetType.TOKENIZED_SECURITY.value,
            decimals=0,
            is_verified=True,
        )
        AssetChainDeployment.objects.create(
            asset=self.asset, chain=SHARE_ASSET_CHAIN, contract_address=self.token.contract_address, decimals=0
        )
        self.service = ShareTokenService()

    def _request(self, recipient):
        request = ShareIssuanceRequest.objects.create(
            token=self.token, recipient_address=recipient, amount=25, reason="Allotment"
        )
        ShareIssuanceRequest.objects.filter(pk=request.pk).update(status=RequestStatus.APPROVED)
        request.refresh_from_db()
        return request

    def _balance(self, value):
        client = Mock()
        client.get_token_balance.return_value = value
        return patch("wallets.services.chain.get_blockchain_client", return_value=client)

    def test_an_allotment_to_a_whitelisted_investor_wallet_writes_the_holding(self):
        WhitelistEntry.objects.create(wallet=self.wallet, status=WhitelistStatus.ACTIVE, is_whitelisted=True)
        request = self._request(self.wallet.address)

        with self._balance(Decimal("25")):
            self.service.execute_request(request)

        request.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.EXECUTED)
        holding = Holding.objects.get(wallet=self.wallet, asset=self.asset)
        self.assertEqual(holding.quantity, Decimal("25"))
        self.assertEqual(holding.snapshots.get().quantity, Decimal("25"))
        self.assertIsNone(holding.market_value)

    def test_a_treasury_entry_with_no_wallet_is_skipped_and_raises_nothing(self):
        treasury = Web3.to_checksum_address("0x" + "7" * 40)
        WhitelistEntry.objects.create(
            address=treasury, label="Treasury", status=WhitelistStatus.ACTIVE, is_whitelisted=True
        )
        request = self._request(treasury)

        with self._balance(Decimal("25")):
            self.service.execute_request(request)

        request.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.EXECUTED)
        self.assertFalse(Holding.objects.filter(asset=self.asset).exists())
        self.assertEqual(ShareIssuance.objects.get(token=self.token).status, IssuanceStatus.COMPLETED)

    def test_a_bookkeeping_failure_never_fails_an_issuance_whose_mint_already_mined(self):
        WhitelistEntry.objects.create(wallet=self.wallet, status=WhitelistStatus.ACTIVE, is_whitelisted=True)
        request = self._request(self.wallet.address)

        with patch("wallets.services.holdings.sync_holding", side_effect=RuntimeError("database gone")) as sync:
            with self.assertLogs("tokens.services.share_token_service", level="ERROR") as logs:
                result = self.service.execute_request(request)

        sync.assert_called_once()
        self.assertIn("Could not record the DEP holding", "\n".join(logs.output))
        self.assertEqual(result["tx_hash"], "0xmint")
        request.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.EXECUTED)
        self.assertEqual(ShareIssuance.objects.get(token=self.token).status, IssuanceStatus.COMPLETED)
        self.assertFalse(Holding.objects.filter(asset=self.asset).exists())

    def test_a_missing_bridged_asset_is_logged_and_leaves_the_issuance_executed(self):
        AssetChainDeployment.objects.filter(asset=self.asset).delete()
        WhitelistEntry.objects.create(wallet=self.wallet, status=WhitelistStatus.ACTIVE, is_whitelisted=True)
        request = self._request(self.wallet.address)

        with self.assertLogs("tokens.services.share_token_service", level="WARNING") as logs:
            self.service.execute_request(request)

        self.assertIn("has no asset on base", "\n".join(logs.output))
        request.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.EXECUTED)
        self.assertFalse(Holding.objects.filter(asset=self.asset).exists())


@override_settings(SHARE_TOKEN_FACTORY_ADDRESS="0x" + "f" * 40, BLOCKCHAIN_OPERATOR_KEY="0xkey")
class BridgeShareAssetsCommandTest(TestCase):
    def setUp(self):
        self.chain = patch(CHAIN_CLIENT).start().return_value
        self.addCleanup(patch.stopall)
        self.tenant = make_tenant("owner")
        self.token = self.tenant.deployed_token
        self.chain.load_contract.return_value.functions.getTokenByIdentifier.return_value.call.return_value = (
            self.token.contract_address
        )

    def _run(self, **options):
        output = StringIO()
        call_command("bridge_share_assets", stdout=output, **options)
        return output.getvalue()

    def test_the_dry_run_writes_nothing(self):
        output = self._run(dry_run=True)

        self.assertIn(f"would bridge {self.tenant.company.name} DEP", output)
        self.assertFalse(AssetChainDeployment.objects.filter(contract_address=self.token.contract_address).exists())

    def test_the_backfill_is_idempotent(self):
        self._run()
        self._run()

        deployment = AssetChainDeployment.objects.get(contract_address=self.token.contract_address)
        self.assertEqual(deployment.asset.symbol, "DEP")
        self.assertTrue(deployment.asset.is_verified)
        self.assertEqual(deployment.asset.asset_type, AssetType.TOKENIZED_SECURITY.value)
