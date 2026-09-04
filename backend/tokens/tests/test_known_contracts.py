from django.test import TestCase, override_settings

from shared.tests.tenants import make_tenant
from tokens.models import Stablecoin
from tokens.services.contracts import known_contract_addresses


class KnownContractAddressesTest(TestCase):
    @override_settings(ATOMIC_SWAP_ADDRESS="0x" + "AB" * 20, SHARE_EXCHANGE_ADDRESS="")
    def test_configured_and_token_contracts_are_lower_cased(self):
        tenant = make_tenant("alice")
        Stablecoin.objects.create(name="Retired", symbol="OLD", contract_address="0x" + "6" * 40, is_active=False)

        known = known_contract_addresses()

        self.assertIn("0x" + "ab" * 20, known)
        self.assertIn(tenant.deployed_token.contract_address.lower(), known)
        self.assertIn(tenant.refs.stablecoin.contract_address.lower(), known)
        self.assertNotIn("0x" + "6" * 40, known)
        self.assertNotIn("", known)
