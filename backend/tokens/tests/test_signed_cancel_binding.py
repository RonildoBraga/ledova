from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from eth_utils import to_checksum_address
from rest_framework.test import APITransactionTestCase

from shared.db import atomic
from shared.utils.typed_data import typed_data_digest
from tokens.exceptions import ChallengeAlreadyUsedException, ChallengeMismatchException
from tokens.models import SigningChallenge, SigningChallengePurpose, TransferOrder
from tokens.models.choices import TransferOrderStatus
from tokens.services.signing_challenge import consume_challenge
from tokens.tests.order_action_fixtures import OTHER_KEY, OWNER, ActionFixtures


class SignedCancelBindingTest(ActionFixtures, APITransactionTestCase):
    def request_challenge(self, order=None):
        response = self.message(order=order)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def post_cancel(self, issued, signer=OWNER, order=None):
        return self.execute("cancel", self.sign(issued, signer), order=order)

    def reopen(self):
        TransferOrder.objects.filter(pk=self.order.pk).update(status=TransferOrderStatus.OPEN)

    def test_a_cancel_signature_is_accepted_once_and_the_order_is_cancelled(self):
        issued = self.request_challenge()
        response = self.post_cancel(issued)
        self.assertEqual(response.status_code, 200, response.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, TransferOrderStatus.CANCELLED)
        self.assertIsNotNone(SigningChallenge.objects.get(digest=issued["challenge"]["digest"]).consumed_at)

    def test_a_spent_action_recovers_without_cancelling_a_reopened_order(self):
        issued = self.request_challenge()
        first = self.post_cancel(issued)
        self.assertEqual(first.status_code, 200)
        self.reopen()
        replay = self.post_cancel(issued)
        self.assertEqual(replay.status_code, 200, replay.content)
        self.assertEqual(replay.json()["result"], first.json()["result"])
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, TransferOrderStatus.OPEN)
        self.assertEqual(len(self.events), 1)
        self.action_id = uuid4()
        other = self.request_challenge()
        stale = {**self.sign(issued), **self.identity()}
        self.assertEqual(self.execute("cancel", stale).status_code, 400)
        self.assertEqual(self.post_cancel(other).status_code, 200)

    def test_a_signature_refused_because_the_order_moved_is_still_spent(self):
        issued = self.request_challenge()
        TransferOrder.objects.filter(pk=self.order.pk).update(status=TransferOrderStatus.MATCHED)
        refused = self.post_cancel(issued)
        self.assertEqual(refused.status_code, 400, refused.content)
        self.assertEqual(refused.json()["refusal"]["code"], "order_cancellation_failed")
        self.assertIsNotNone(SigningChallenge.objects.get(digest=issued["challenge"]["digest"]).consumed_at)
        self.reopen()
        replay = self.post_cancel(issued)
        self.assertEqual(replay.status_code, 400, replay.content)
        self.assertEqual(replay.json()["refusal"], refused.json()["refusal"])
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, TransferOrderStatus.OPEN)

    def test_a_challenge_issued_for_another_order_is_refused(self):
        issued = self.request_challenge()
        response = self.post_cancel(issued, order=self.tenant.order)
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["code"], "action_intent_conflict")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, TransferOrderStatus.OPEN)
        self.assertEqual(self.post_cancel(issued).status_code, 200)

    def test_a_signature_from_another_key_is_refused(self):
        issued = self.request_challenge()
        response = self.post_cancel(issued, OTHER_KEY)
        self.assertEqual(response.status_code, 403, response.content)
        self.assert_pending(self.sign(issued))
        self.assertEqual(self.post_cancel(issued).status_code, 200)

    def test_an_expired_challenge_is_refused_and_says_so(self):
        issued = self.request_challenge()
        deadline = SigningChallenge.objects.get(digest=issued["challenge"]["digest"]).expires_at
        with patch("tokens.models.signing_challenge.timezone.now", return_value=deadline + timedelta(seconds=1)):
            response = self.post_cancel(issued)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["code"], "challenge_expired")
        self.assert_pending(self.sign(issued))
        refreshed = self.request_challenge()
        self.assertEqual(refreshed["actionId"], issued["actionId"])
        self.assertEqual(self.post_cancel(refreshed).status_code, 200)

    def test_a_digest_nobody_issued_is_refused(self):
        issued = self.request_challenge()
        response = self.execute(
            "cancel", {**self.identity(), "digest": "0x" + "ee" * 32, "signature": "0x" + "ab" * 65}
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["code"], "challenge_unknown")
        self.assertEqual(self.post_cancel(issued).status_code, 200)

    def test_the_issued_challenge_names_the_chain_and_the_verifying_contract(self):
        issued = self.request_challenge()["challenge"]
        self.assertEqual(issued["domain"]["chainId"], settings.BLOCKCHAIN_CHAIN_ID)
        self.assertEqual(
            issued["domain"]["verifyingContract"], to_checksum_address(self.tenant.deployed_token.contract_address)
        )
        self.assertEqual(issued["message"]["orderUuid"], str(self.order.uuid))
        self.assertEqual(issued["message"]["wallet"], OWNER.address)
        self.assertEqual(issued["message"]["actionId"], str(self.action_id))
        self.assertEqual(issued["message"]["ownerAccountUuid"], str(self.tenant.account.pk))
        self.assertEqual(issued["message"]["walletUuid"], str(self.wallet.pk))
        self.assertEqual(issued["message"]["tokenUuid"], str(self.order.token_id))
        self.assertEqual(issued["message"]["protocolVersion"], "1")
        self.assertIn("OrderCancelV1", issued["types"])

    def test_no_number_in_the_challenge_can_be_rounded_by_a_javascript_client(self):
        issued = self.request_challenge()["challenge"]

        def numbers(value):
            if isinstance(value, bool):
                return []
            if isinstance(value, (int, float)):
                return [value]
            if isinstance(value, dict):
                return [n for item in value.values() for n in numbers(item)]
            if isinstance(value, list):
                return [n for item in value for n in numbers(item)]
            return []

        self.assertEqual([n for n in numbers(issued) if abs(n) > 2**53 - 1], [])
        self.assertIsInstance(issued["message"]["nonce"], str)
        self.assertIsInstance(issued["message"]["deadline"], str)

    def test_a_signature_over_the_wire_form_matches_the_stored_digest(self):
        issued = self.request_challenge()["challenge"]
        stored = SigningChallenge.objects.get(digest=issued["digest"])
        self.assertEqual(issued["message"], stored.payload["message"])
        self.assertEqual(issued["digest"], typed_data_digest(issued["domain"], issued["types"], issued["message"]))

    def test_two_challenges_for_one_action_carry_different_nonces(self):
        first = self.request_challenge()
        second = self.request_challenge()
        self.assertEqual(first["actionId"], second["actionId"])
        self.assertNotEqual(first["challenge"]["digest"], second["challenge"]["digest"])
        self.assertNotEqual(first["challenge"]["message"]["nonce"], second["challenge"]["message"]["nonce"])

    def test_a_cancel_challenge_cannot_authorise_another_action(self):
        issued = self.request_challenge()
        with self.assertRaises(ChallengeMismatchException), atomic():
            consume_challenge(
                issued["challenge"]["digest"],
                SigningChallengePurpose.ORDER_MODIFY,
                OWNER.address,
                self.sign(issued)["signature"],
                order=self.order,
                action=self.journal(),
            )
        self.assertEqual(self.post_cancel(issued).status_code, 200)

    def test_a_challenge_is_spendable_exactly_once_at_the_service_boundary(self):
        issued = self.request_challenge()
        signed = self.sign(issued)
        with atomic():
            challenge = consume_challenge(
                signed["digest"],
                SigningChallengePurpose.ORDER_CANCEL,
                OWNER.address,
                signed["signature"],
                order=self.order,
                action=self.journal(),
            )
            challenge.mark_consumed(signed["signature"])
        with self.assertRaises(ChallengeAlreadyUsedException), atomic():
            consume_challenge(
                signed["digest"],
                SigningChallengePurpose.ORDER_CANCEL,
                OWNER.address,
                signed["signature"],
                order=self.order,
                action=self.journal(),
            )
