"""Pins the broadcast body key both apps send: `signedTransaction` reaches the view as `signed_transaction`."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from feature_flags.models import FeatureFlag
from tokens.tests.test_signed_transactions import CONTRACT, sign_legacy

User = get_user_model()

TX_HASH = "0x" + "f" * 64


class TradingTransferBroadcastContractTest(APITestCase):
    url = "/api/v1/trading/transfers/broadcast/"

    def setUp(self):
        FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
        self.client.force_authenticate(User.objects.create_user(email="signer@example.test", password="pw-12345678"))

    @override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT)
    @patch("tokens.views.trading_transfer.TransferService")
    def test_camel_case_key_reaches_the_service_and_the_receipt_is_camel_cased(self, service_class):
        service_class.return_value.broadcast_transfer.return_value = (TX_HASH, {"blockNumber": 7, "gasUsed": 21000})
        signed = sign_legacy()

        response = self.client.post(self.url, {"signedTransaction": signed}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"txHash": TX_HASH, "blockNumber": 7, "gasUsed": 21000})
        service_class.return_value.broadcast_transfer.assert_called_once_with(signed)

    @patch("tokens.views.trading_transfer.TransferService")
    def test_snake_case_key_with_a_short_suffix_is_not_converted(self, service_class):
        response = self.client.post(self.url, {"signed_tx": "0x02"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"signedTransaction": ["This field is required."]})
        service_class.assert_not_called()
