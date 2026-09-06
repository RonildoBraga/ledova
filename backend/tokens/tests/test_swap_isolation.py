from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from feature_flags.models import FeatureFlag
from tokens.views.swap import SwapOrderViewSet

User = get_user_model()


class SwapQuerysetFailsClosedTest(APITestCase):

    def setUp(self):
        FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
        self.user = User.objects.create_user(
            email="swap-scope@example.test", password="pw-12345678", is_active=True, is_email_verified=True
        )

    def test_the_default_queryset_carries_no_rows_for_anyone(self):
        self.assertFalse(SwapOrderViewSet().get_queryset().exists())

    def test_the_listing_still_answers_from_the_callers_authorised_wallets(self):
        with patch("tokens.views.swap.resolve_verified_evm_wallets") as resolve:
            resolve.return_value.wallet_ids = []
            with patch("tokens.views.swap.AtomicSwapService") as service:
                service.return_value.get_pending_swaps_for_wallet_ids.return_value = SwapOrderViewSet().get_queryset()
                self.client.force_authenticate(self.user)
                response = self.client.get("/api/v1/trading/swaps/?wallet_address=0x" + "a" * 40)

        self.assertEqual(response.status_code, 200)
        service.return_value.get_pending_swaps_for_wallet_ids.assert_called_once_with([])

    def test_the_listing_refuses_without_a_wallet_address(self):
        self.client.force_authenticate(self.user)

        response = self.client.get("/api/v1/trading/swaps/")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"walletAddress": "This query parameter is required."})
