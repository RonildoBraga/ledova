from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings

from shared.tests.tenants import make_tenant
from tokens.services import AtomicSwapService

CONTRACT = "0x" + "5a" * 20


@override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT)
class SwapTypedDataIsSignableTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("signable")
        self.swap = self.tenant.swap

    def typed_data(self):
        with patch("tokens.services.atomic_swap_service.get_base_chain_client") as client, patch(
            "tokens.services.atomic_swap_service.WhitelistService"
        ):
            client.return_value.chain_id = 84532
            return AtomicSwapService().get_typed_data(self.swap)

    def price_an_eighteen_decimal_swap(self):
        asset = self.swap.payment_asset
        asset.decimals = 18
        asset.save(update_fields=["decimals"])
        self.swap = AtomicSwapService().create_swap_order(
            self.tenant.order, self.tenant.counter_order, share_amount=1, price_per_share=Decimal("2.50")
        )

    def test_the_amounts_the_client_signs_match_the_amounts_sent_to_the_contract(self):
        self.price_an_eighteen_decimal_swap()
        message = self.typed_data()["message"]

        self.assertEqual(int(message["paymentAmount"]), self.swap.payment_amount)
        self.assertEqual(int(message["shareAmount"]), self.swap.share_amount)
        self.assertEqual(int(message["nonce"]), self.swap.nonce)
