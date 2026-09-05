from django.test import TestCase

from assets.models import Asset, AssetChainDeployment
from operators.exceptions import SettlementAssetNotDeployedException
from operators.models import Operator, ReceivingChain
from operators.settlement import (
    deployment_for,
    require_deployment,
    settlement_assets,
    settlement_deployments,
)

BASE_ADDRESS = "0x" + "b" * 40
ETHEREUM_ADDRESS = "0x" + "e" * 40


def asset(symbol="AUDY", asset_type="stablecoin", decimals=2):
    return Asset.objects.create(symbol=symbol, name=f"{symbol} dollar", asset_type=asset_type, decimals=decimals)


class RequireDeploymentTest(TestCase):
    def setUp(self):
        self.operator = Operator.get()
        self.asset = asset()

    def test_an_asset_with_no_deployment_at_all_is_refused(self):
        self.assertIsNone(deployment_for(self.asset))
        with self.assertRaises(SettlementAssetNotDeployedException) as ctx:
            require_deployment(self.asset)
        self.assertEqual(str(ctx.exception.detail), "AUDY has no active deployment with a contract address on base.")

    def test_an_inactive_deployment_is_refused(self):
        AssetChainDeployment.objects.create(
            asset=self.asset, chain="base", contract_address=BASE_ADDRESS, decimals=2, is_active=False
        )
        with self.assertRaises(SettlementAssetNotDeployedException):
            require_deployment(self.asset)

    def test_a_deployment_without_a_contract_address_is_refused(self):
        deployment = AssetChainDeployment.objects.create(asset=self.asset, chain="base", decimals=2)
        with self.assertRaises(SettlementAssetNotDeployedException):
            require_deployment(self.asset)
        deployment.contract_address = ""
        deployment.save(update_fields=["contract_address"])
        with self.assertRaises(SettlementAssetNotDeployedException):
            require_deployment(self.asset)

    def test_a_deployment_on_another_chain_is_refused(self):
        AssetChainDeployment.objects.create(
            asset=self.asset, chain="ethereum", contract_address=ETHEREUM_ADDRESS, decimals=2
        )
        with self.assertRaises(SettlementAssetNotDeployedException):
            require_deployment(self.asset)

        self.operator.receiving_wallet_chain = ReceivingChain.ETHEREUM
        self.operator.save(update_fields=["receiving_wallet_chain"])
        self.assertEqual(require_deployment(self.asset).contract_address, ETHEREUM_ADDRESS)

    def test_the_receiving_chain_deployment_is_returned_not_the_alphabetically_first_one(self):
        AssetChainDeployment.objects.create(asset=self.asset, chain="base", contract_address=BASE_ADDRESS, decimals=2)
        AssetChainDeployment.objects.create(
            asset=self.asset, chain="ethereum", contract_address=ETHEREUM_ADDRESS, decimals=2
        )
        self.operator.receiving_wallet_chain = ReceivingChain.ETHEREUM
        self.operator.save(update_fields=["receiving_wallet_chain"])

        self.assertEqual(self.asset.contract_address, BASE_ADDRESS)
        self.assertEqual(require_deployment(self.asset).contract_address, ETHEREUM_ADDRESS)
        self.assertEqual(deployment_for(self.asset).chain, "ethereum")


class SettlementAssetsTest(TestCase):
    def setUp(self):
        self.operator = Operator.get()
        self.audy = asset()
        self.deployment = AssetChainDeployment.objects.create(
            asset=self.audy, chain="base", contract_address=BASE_ADDRESS, decimals=2
        )

    def test_only_supported_deployed_and_active_assets_are_listed(self):
        self.assertEqual(list(settlement_assets()), [])

        self.operator.supported_settlement_assets.add(self.audy)
        self.assertEqual(list(settlement_assets()), [self.audy])
        self.assertEqual([row.contract_address for row in settlement_deployments()], [BASE_ADDRESS])

        Asset.objects.filter(pk=self.audy.pk).update(is_active=False)
        self.assertEqual(list(settlement_assets()), [])

        Asset.objects.filter(pk=self.audy.pk).update(is_active=True)
        AssetChainDeployment.objects.filter(pk=self.deployment.pk).update(chain="ethereum")
        self.assertEqual(list(settlement_assets()), [])
