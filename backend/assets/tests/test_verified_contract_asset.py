from django.test import TestCase

from assets.models import Asset, AssetChainDeployment, AssetType
from assets.services.identity import quarantine_unknown_token, verified_contract_asset
from assets.services.sync import PRICED_ASSET_TYPES

SHARE = "0x" + "5e" * 20
OTHER_SHARE = "0x" + "77" * 20


def bridge(contract_address=SHARE, symbol="ORD", name="Acme Pty Ltd Ordinary shares"):
    return verified_contract_asset(
        chain="base",
        contract_address=contract_address,
        symbol=symbol,
        name=name,
        decimals=0,
        asset_type=AssetType.TOKENIZED_SECURITY.value,
    )


class VerifiedContractAssetTest(TestCase):
    def test_a_fresh_bridge_writes_one_verified_asset_and_one_deployment(self):
        asset = bridge()

        self.assertEqual(
            (asset.symbol, asset.name, asset.asset_type, asset.decimals),
            ("ORD", "Acme Pty Ltd Ordinary shares", AssetType.TOKENIZED_SECURITY.value, 0),
        )
        self.assertTrue(asset.is_verified)
        self.assertIsNone(asset.current_price)
        self.assertNotIn(asset.asset_type, PRICED_ASSET_TYPES)
        deployment = asset.chain_deployments.get()
        self.assertEqual((deployment.chain, deployment.contract_address, deployment.decimals), ("base", SHARE, 0))

    def test_running_the_bridge_twice_adopts_its_own_row_instead_of_writing_a_second(self):
        first = bridge()
        second = bridge()

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Asset.objects.filter(asset_type=AssetType.TOKENIZED_SECURITY.value).count(), 1)
        self.assertEqual(AssetChainDeployment.objects.filter(contract_address=SHARE).count(), 1)

    def test_a_quarantined_row_is_adopted_and_promoted_rather_than_duplicated(self):
        quarantined = quarantine_unknown_token(chain="base", contract_address=SHARE.upper(), symbol="ORD", decimals=18)
        self.assertEqual(
            (quarantined.asset_type, quarantined.decimals, quarantined.is_verified), ("erc20_token", 18, False)
        )

        adopted = bridge()

        self.assertEqual(adopted.pk, quarantined.pk)
        self.assertEqual(Asset.objects.filter(chain_deployments__contract_address__iexact=SHARE).count(), 1)
        self.assertEqual(
            (adopted.asset_type, adopted.decimals, adopted.is_verified, adopted.name),
            (AssetType.TOKENIZED_SECURITY.value, 0, True, "Acme Pty Ltd Ordinary shares"),
        )
        deployment = adopted.chain_deployments.get()
        self.assertEqual((deployment.contract_address, deployment.decimals), (SHARE.upper(), 0))

    def test_a_symbol_already_taken_falls_back_to_a_suffixed_one(self):
        bridge()

        second = bridge(contract_address=OTHER_SHARE, symbol="ORD", name="Beta Pty Ltd Ordinary shares")

        self.assertEqual(second.symbol, "ORD-777777")
        self.assertTrue(second.is_verified)
        self.assertEqual(Asset.objects.filter(symbol__startswith="ORD").count(), 2)

    def test_a_reserved_symbol_is_never_claimed_by_a_share_class(self):
        asset = bridge(symbol="AUDY", name="Acme Pty Ltd AUDY shares")

        self.assertNotEqual(asset.symbol, "AUDY")
        self.assertTrue(asset.symbol.startswith("AUDY-"))
        self.assertFalse(Asset.objects.filter(symbol="AUDY").exists())

    def test_a_long_name_is_truncated_to_the_column(self):
        asset = bridge(name="N" * 400)

        self.assertEqual(len(asset.name), 255)
