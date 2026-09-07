from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.utils import timezone
from eth_account import Account
from eth_utils import to_checksum_address
from rest_framework.test import APITestCase

from feature_flags.models import FeatureFlag
from shared.tests.tenants import make_tenant
from shared.utils.typed_data import signable_message
from tokens.models import SigningChallenge

OWNER = Account.from_key("0x" + "31" * 32)
STRANGER = Account.from_key("0x" + "47" * 32)
BASE = "/api/v1/trading/orders/"


class SignedCreateBindingTest(APITestCase):

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
        self.tenant = make_tenant("creator")
        self.tenant.wallet.address = OWNER.address
        self.tenant.wallet.save(update_fields=["address"])
        self.client.force_authenticate(self.tenant.user)

    def order_body(self, **overrides):
        body = {
            "token": str(self.tenant.deployed_token.uuid),
            "order_type": "sell",
            "wallet_uuid": str(self.tenant.wallet.uuid),
            "wallet_address": OWNER.address,
            "quantity": 5,
            "price_per_share": "2.50",
        }
        body.update(overrides)
        return body

    def request_challenge(self, **overrides):
        response = self.client.post(f"{BASE}create/message/", self.order_body(**overrides), format="json")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    @staticmethod
    def sign(issued, account=OWNER):
        return account.sign_message(
            signable_message(issued["domain"], issued["types"], issued["message"])
        ).signature.hex()

    def post_create(self, issued, signature, **overrides):
        return self.client.post(
            f"{BASE}create/",
            self.order_body(digest=issued["digest"], signature=signature, **overrides),
            format="json",
        )

    def test_the_message_route_answers_a_challenge_rather_than_five_hundred(self):
        response = self.client.post(f"{BASE}create/message/", self.order_body(), format="json")

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertIn("digest", body)
        self.assertIn("OrderCreate", body["types"])
        self.assertEqual(body["message"]["tokenUuid"], str(self.tenant.deployed_token.uuid))
        self.assertEqual(body["message"]["quantity"], "5")
        self.assertEqual(body["message"]["pricePerShare"], "2.50")

    def test_the_message_route_refuses_a_malformed_body(self):
        response = self.client.post(f"{BASE}create/message/", {"order_type": "sell"}, format="json")

        self.assertEqual(response.status_code, 400, response.content)

    def test_the_uint256_fields_go_on_the_wire_as_strings(self):
        message = self.request_challenge()["message"]

        for field in ("quantity", "nonce", "deadline"):
            self.assertIsInstance(message[field], str, field)

    @patch("tokens.views.trading_order.TokenTransferService")
    def test_a_create_signature_is_accepted_once(self, transfers):
        transfers.return_value.create_order_and_match.return_value = (self.tenant.order, None)
        issued = self.request_challenge()

        response = self.post_create(issued, self.sign(issued))

        self.assertEqual(response.status_code, 201, response.content)
        self.assertIsNotNone(SigningChallenge.objects.get(digest=issued["digest"]).consumed_at)

    @patch("tokens.views.trading_order.TokenTransferService")
    def test_a_spent_create_signature_cannot_open_a_second_order(self, transfers):
        transfers.return_value.create_order_and_match.return_value = (self.tenant.order, None)
        issued = self.request_challenge()
        signature = self.sign(issued)
        self.assertEqual(self.post_create(issued, signature).status_code, 201)

        replay = self.post_create(issued, signature)

        self.assertEqual(replay.status_code, 409, replay.content)
        self.assertEqual(transfers.return_value.create_order_and_match.call_count, 1)

    @patch("tokens.views.trading_order.TokenTransferService")
    def test_a_signature_for_one_price_cannot_place_an_order_at_another(self, transfers):
        transfers.return_value.create_order_and_match.return_value = (self.tenant.order, None)
        issued = self.request_challenge()

        response = self.post_create(issued, self.sign(issued), price_per_share="0.01")

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["code"], "challenge_mismatch")
        transfers.return_value.create_order_and_match.assert_not_called()

    @patch("tokens.views.trading_order.TokenTransferService")
    def test_a_signature_for_one_quantity_cannot_place_an_order_for_another(self, transfers):
        transfers.return_value.create_order_and_match.return_value = (self.tenant.order, None)
        issued = self.request_challenge()

        response = self.post_create(issued, self.sign(issued), quantity=500)

        self.assertEqual(response.status_code, 400, response.content)
        transfers.return_value.create_order_and_match.assert_not_called()

    @patch("tokens.views.trading_order.TokenTransferService")
    def test_a_signature_for_a_partial_fill_cannot_place_an_all_or_nothing_order(self, transfers):
        transfers.return_value.create_order_and_match.return_value = (self.tenant.order, None)
        issued = self.request_challenge(min_quantity=0)

        response = self.post_create(issued, self.sign(issued), min_quantity=5)

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["code"], "challenge_mismatch")
        transfers.return_value.create_order_and_match.assert_not_called()

    def test_the_challenge_binds_how_the_order_may_be_filled(self):
        issued = self.request_challenge(min_quantity=3)

        self.assertEqual(issued["message"]["minQuantity"], "3")
        self.assertIn("minQuantity", [field["name"] for field in issued["types"]["OrderCreate"]])

    @patch("tokens.views.trading_order.TokenTransferService")
    def test_a_signature_from_another_key_is_refused(self, transfers):
        issued = self.request_challenge()

        response = self.post_create(issued, self.sign(issued, STRANGER))

        self.assertEqual(response.status_code, 403, response.content)
        transfers.return_value.create_order_and_match.assert_not_called()

    @patch("tokens.views.trading_order.TokenTransferService")
    def test_an_expired_challenge_is_refused_and_says_so(self, transfers):
        issued = self.request_challenge()
        SigningChallenge.objects.filter(digest=issued["digest"]).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        response = self.post_create(issued, self.sign(issued))

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["code"], "challenge_expired")
        transfers.return_value.create_order_and_match.assert_not_called()

    def test_the_challenge_names_the_wallet_it_was_issued_to(self):
        issued = self.request_challenge()

        self.assertEqual(issued["message"]["wallet"], to_checksum_address(OWNER.address))
        self.assertEqual(issued["message"]["orderType"], "sell")
        self.assertEqual(Decimal(issued["message"]["pricePerShare"]), Decimal("2.50"))
