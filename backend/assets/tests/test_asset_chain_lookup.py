from django.test import TestCase

from assets.models import Asset, AssetChainDeployment, AssetType

SHARE = "0x" + "5e" * 20
OTHER = "0x" + "77" * 20


class AssetChainLookupTest(TestCase):
    def setUp(self):
        self.asset = Asset.objects.create(
            name="Acme Pty Ltd Ordinary shares",
            symbol="ORD",
            asset_type=AssetType.TOKENIZED_SECURITY.value,
            decimals=0,
        )
        self.deployment = AssetChainDeployment.objects.create(
            asset=self.asset, chain="base", contract_address=SHARE, decimals=0
        )

    def test_it_finds_the_asset_behind_a_deployment(self):
        self.assertEqual(Asset.get_by_chain_and_contract("base", SHARE), self.asset)

    def test_the_address_is_matched_case_insensitively(self):
        self.assertEqual(Asset.get_by_chain_and_contract("base", SHARE.upper()), self.asset)

    def test_another_chain_does_not_match(self):
        self.assertIsNone(Asset.get_by_chain_and_contract("ethereum", SHARE))

    def test_another_address_does_not_match(self):
        self.assertIsNone(Asset.get_by_chain_and_contract("base", OTHER))

    def test_an_inactive_deployment_is_not_reachable(self):
        self.deployment.is_active = False
        self.deployment.save(update_fields=["is_active"])

        self.assertIsNone(Asset.get_by_chain_and_contract("base", SHARE))

    def test_it_does_not_answer_with_an_asset_whose_other_chain_matches_the_address(self):
        other_asset = Asset.objects.create(
            name="Beta Pty Ltd Ordinary shares",
            symbol="BET",
            asset_type=AssetType.TOKENIZED_SECURITY.value,
            decimals=0,
        )
        AssetChainDeployment.objects.create(asset=other_asset, chain="ethereum", contract_address=OTHER, decimals=0)

        self.assertEqual(Asset.get_by_chain_and_contract("base", SHARE), self.asset)
        self.assertIsNone(Asset.get_by_chain_and_contract("base", OTHER))
