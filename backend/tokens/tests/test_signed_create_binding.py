from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from eth_utils import to_checksum_address
from rest_framework.test import APITransactionTestCase

from shared.db import use_operator
from shared.utils.typed_data import signable_message
from tokens.models import SigningChallenge, TransferOrder
from tokens.tests.order_submission_fixtures import (
    BASE,
    OTHER_KEY,
    OWNER,
    SubmissionFixtures,
)


class SignedCreateBindingTest(SubmissionFixtures, APITransactionTestCase):
    def order_body(self, **overrides):
        return self.body(**{"order_type": "sell", "quantity": 5, **overrides})

    def request_challenge(self, **overrides):
        return self.issue(self.order_body(**overrides))

    @staticmethod
    def sign(issued, account=OWNER):
        return account.sign_message(
            signable_message(issued["domain"], issued["types"], issued["message"])
        ).signature.to_0x_hex()

    def post_create(self, issued, signature, **overrides):
        return self.create(self.order_body(digest=issued["digest"], signature=signature, **overrides))

    def test_the_message_route_answers_a_challenge_rather_than_five_hundred(self):
        body = self.request_challenge()
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

    def test_a_create_signature_is_accepted_once(self):
        issued = self.request_challenge()
        response = self.post_create(issued, self.sign(issued))
        self.assertEqual(response.status_code, 201, response.content)
        with use_operator():
            self.assertIsNotNone(SigningChallenge.objects.get(digest=issued["digest"]).consumed_at)

    def test_a_spent_create_signature_recovers_the_same_order(self):
        issued = self.request_challenge()
        signature = self.sign(issued)
        first = self.post_create(issued, signature)
        self.assertEqual(first.status_code, 201, first.content)
        replay = self.post_create(issued, signature)
        self.assertEqual(replay.status_code, 200, replay.content)
        self.assertEqual(first.json(), replay.json())
        with use_operator():
            self.assertEqual(TransferOrder.objects.count(), self.initial_order_count + 1)

    def test_a_signature_for_one_price_cannot_place_an_order_at_another(self):
        issued = self.request_challenge()
        response = self.post_create(issued, self.sign(issued), price_per_share="0.01")
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["code"], "submission_conflict")
        self.balance.get_token_balance.assert_not_called()

    def test_a_signature_for_one_quantity_cannot_place_an_order_for_another(self):
        issued = self.request_challenge()
        response = self.post_create(issued, self.sign(issued), quantity=500)
        self.assertEqual(response.status_code, 409, response.content)
        self.balance.get_token_balance.assert_not_called()

    def test_a_signature_for_a_partial_fill_cannot_place_an_all_or_nothing_order(self):
        issued = self.request_challenge(min_quantity=0)
        response = self.post_create(issued, self.sign(issued), min_quantity=5)
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["code"], "submission_conflict")
        self.balance.get_token_balance.assert_not_called()

    def test_the_challenge_binds_how_the_order_may_be_filled(self):
        issued = self.request_challenge(min_quantity=3)
        self.assertEqual(issued["message"]["minQuantity"], "3")
        self.assertIn("minQuantity", [field["name"] for field in issued["types"]["OrderCreate"]])

    def test_a_signature_from_another_key_is_refused(self):
        issued = self.request_challenge()
        response = self.post_create(issued, self.sign(issued, OTHER_KEY))
        self.assertEqual(response.status_code, 403, response.content)
        self.balance.get_token_balance.assert_not_called()

    def test_an_expired_challenge_is_refused_and_says_so(self):
        issued = self.request_challenge()
        with use_operator():
            deadline = SigningChallenge.objects.get(digest=issued["digest"]).expires_at
        with patch("tokens.models.signing_challenge.timezone.now", return_value=deadline + timedelta(seconds=1)):
            response = self.post_create(issued, self.sign(issued))
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["code"], "challenge_expired")
        self.balance.get_token_balance.assert_not_called()

    def test_the_challenge_names_the_wallet_it_was_issued_to(self):
        issued = self.request_challenge()
        self.assertEqual(issued["message"]["wallet"], to_checksum_address(OWNER.address))
        self.assertEqual(issued["message"]["orderType"], "sell")
        self.assertEqual(Decimal(issued["message"]["pricePerShare"]), Decimal("2.50"))
