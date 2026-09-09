from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from eth_account import Account
from rest_framework.test import APITestCase

from feature_flags.models import FeatureFlag
from tokens.tests.test_signed_transactions import (
    CHAIN_ID,
    CONTRACT,
    SIGNER,
    _hex,
    sign_legacy,
)
from users.models import UserAccount, UserProfile
from wallets.models import Wallet

User = get_user_model()

TX_HASH = "0x" + "f" * 64
STRANGER = Account.from_key("0x" + "22" * 32)


@override_settings(BLOCKCHAIN_CHAIN_ID=CHAIN_ID)
class TradingTransferBroadcastContractTest(APITestCase):
    url = "/api/v1/trading/transfers/broadcast/"

    def setUp(self):
        FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
        self.user = User.objects.create_user(email="signer@example.test", password="pw-12345678")
        profile = UserProfile.objects.create(user=self.user)
        self.account = UserAccount.objects.create()
        self.account.user_profiles.add(profile)
        self.wallet = Wallet.objects.create(
            user_account=self.account, address=SIGNER.address, chain="base", verification_status="VERIFIED"
        )
        self.client.force_authenticate(self.user)

    @override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT)
    @patch("tokens.views.trading_transfer.TokenTransferService")
    def test_camel_case_key_reaches_the_service_and_the_receipt_is_camel_cased(self, service_class):
        service_class.return_value.broadcast_transfer.return_value = (TX_HASH, {"blockNumber": 7, "gasUsed": 21000})
        signed = sign_legacy()

        response = self.client.post(self.url, {"signedTransaction": signed}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"txHash": TX_HASH, "blockNumber": 7, "gasUsed": 21000})
        service_class.return_value.broadcast_transfer.assert_called_once_with(signed)

    @patch("tokens.views.trading_transfer.TokenTransferService")
    def test_snake_case_key_with_a_short_suffix_is_not_converted(self, service_class):
        response = self.client.post(self.url, {"signed_tx": "0x02"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"signedTransaction": ["This field is required."]})
        service_class.assert_not_called()

    @override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT)
    @patch("tokens.views.trading_transfer.TokenTransferService")
    def test_a_transaction_signed_by_a_key_the_caller_does_not_hold_is_refused(self, service_class):
        service_class.return_value.broadcast_transfer.return_value = (TX_HASH, {"blockNumber": 7})
        stranger_signed = _hex(
            STRANGER.sign_transaction(
                {
                    "nonce": 1,
                    "gasPrice": 10**9,
                    "gas": 100_000,
                    "to": CONTRACT,
                    "value": 5,
                    "data": b"",
                    "chainId": CHAIN_ID,
                }
            )
        )

        response = self.client.post(self.url, {"signedTransaction": stranger_signed}, format="json")

        self.assertEqual(response.status_code, 404, response.content)
        service_class.assert_not_called()

    @override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT)
    @patch("tokens.views.trading_transfer.TokenTransferService")
    def test_an_unverified_wallet_at_the_signing_address_is_not_enough(self, service_class):
        service_class.return_value.broadcast_transfer.return_value = (TX_HASH, {"blockNumber": 7})
        self.wallet.verification_status = "PENDING"
        self.wallet.save(update_fields=["verification_status"])

        response = self.client.post(self.url, {"signedTransaction": sign_legacy()}, format="json")

        self.assertEqual(response.status_code, 404, response.content)
        service_class.assert_not_called()
