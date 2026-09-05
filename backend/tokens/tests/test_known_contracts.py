from django.test import TestCase, override_settings

from assets.models import Asset, AssetChainDeployment
from shared.tests.tenants import make_tenant
from tokens.services.contracts import known_contract_addresses


class KnownContractAddressesTest(TestCase):
    @override_settings(ATOMIC_SWAP_ADDRESS="0x" + "AB" * 20, SHARE_EXCHANGE_ADDRESS="")
    def test_configured_and_token_contracts_are_lower_cased(self):
        tenant = make_tenant("alice")
        retired = Asset.objects.create(
            symbol="OLD", name="Retired", asset_type="stablecoin", decimals=2, is_active=False
        )
        AssetChainDeployment.objects.create(asset=retired, chain="base", contract_address="0x" + "6" * 40, decimals=2)

        known = known_contract_addresses()

        self.assertIn("0x" + "ab" * 20, known)
        self.assertIn(tenant.deployed_token.contract_address.lower(), known)
        self.assertIn(tenant.refs.stablecoin.chain_deployments.get().contract_address.lower(), known)
        self.assertNotIn("0x" + "6" * 40, known)
        self.assertNotIn("", known)
