from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings

from shared.tests.signable import assert_signable, unsafe_numbers
from shared.tests.tenants import make_tenant
from tokens.models import SwapOrder
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
        SwapOrder.objects.filter(pk=self.swap.pk).update(
            payment_amount=int(Decimal("2.50") * (10**18)),
        )
        self.swap.refresh_from_db()

    def test_an_ordinary_swap_carries_no_number_a_javascript_client_would_round(self):
        assert_signable(self, self.typed_data())

    def test_a_swap_priced_in_an_eighteen_decimal_asset_is_still_signable(self):
        self.price_an_eighteen_decimal_swap()

        self.assertGreater(self.swap.payment_amount, 2**53 - 1)
        assert_signable(self, self.typed_data())

    def test_the_amounts_the_client_signs_match_the_amounts_sent_to_the_contract(self):
        self.price_an_eighteen_decimal_swap()
        message = self.typed_data()["message"]

        self.assertEqual(int(message["paymentAmount"]), self.swap.payment_amount)
        self.assertEqual(int(message["shareAmount"]), self.swap.share_amount)
        self.assertEqual(int(message["nonce"]), self.swap.nonce)

    def test_the_helper_recognises_a_number_that_would_be_rounded(self):
        self.assertEqual(unsafe_numbers({"a": {"b": [2**53]}}), [2**53])
        self.assertEqual(unsafe_numbers({"a": {"b": [2**53 - 1]}}), [])
