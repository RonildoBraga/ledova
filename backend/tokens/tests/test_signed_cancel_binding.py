from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from eth_account import Account
from eth_utils import to_checksum_address
from rest_framework.test import APITestCase

from feature_flags.models import FeatureFlag
from shared.tests.tenants import make_tenant
from shared.utils.typed_data import signable_message
from tokens.exceptions import ChallengeAlreadyUsedException, ChallengeMismatchException
from tokens.models import SigningChallenge, SigningChallengePurpose, TransferOrder
from tokens.models.choices import TransferOrderStatus, TransferOrderType
from tokens.services.signing_challenge import consume_challenge, issue_challenge

OWNER = Account.from_key("0x" + "17" * 32)
STRANGER = Account.from_key("0x" + "29" * 32)


class SignedCancelBindingTest(APITestCase):

    def setUp(self):
        FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
        self.tenant = make_tenant("canceller")
        self.tenant.wallet.address = OWNER.address
        self.tenant.wallet.save(update_fields=["address"])
        self.order = self._order()
        self.client.force_authenticate(self.tenant.user)

    def _order(self):
        return TransferOrder.objects.create(
            order_type=TransferOrderType.SELL,
            token=self.tenant.deployed_token,
            payment_asset=self.tenant.refs.stablecoin,
            wallet=self.tenant.wallet,
            owner_account=self.tenant.account,
            wallet_address=OWNER.address,
            quantity=10,
            price_per_share=Decimal("1.50"),
        )

    def request_challenge(self, order=None):
        order = order or self.order
        response = self.client.get(f"/api/v1/trading/orders/{order.uuid}/cancel/message/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    @staticmethod
    def sign(issued, account=OWNER):
        encoded = signable_message(issued["domain"], issued["types"], issued["message"])
        return account.sign_message(encoded).signature.hex()

    def post_cancel(self, digest, signature, order=None):
        order = order or self.order
        return self.client.post(
            f"/api/v1/trading/orders/{order.uuid}/cancel/",
            {"digest": digest, "signature": signature},
            format="json",
        )

    def reopen(self, order=None):
        order = order or self.order
        TransferOrder.objects.filter(pk=order.pk).update(status=TransferOrderStatus.OPEN)

    def test_a_cancel_signature_is_accepted_once_and_the_order_is_cancelled(self):
        issued = self.request_challenge()

        response = self.post_cancel(issued["digest"], self.sign(issued))

        self.assertEqual(response.status_code, 200, response.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, TransferOrderStatus.CANCELLED)
        self.assertIsNotNone(SigningChallenge.objects.get(digest=issued["digest"]).consumed_at)

    def test_a_spent_cancel_signature_is_refused_even_when_the_order_is_cancellable_again(self):
        issued = self.request_challenge()
        signature = self.sign(issued)
        self.assertEqual(self.post_cancel(issued["digest"], signature).status_code, 200)

        self.reopen()
        replay = self.post_cancel(issued["digest"], signature)

        self.assertEqual(replay.status_code, 409, replay.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, TransferOrderStatus.OPEN)

    def test_a_challenge_issued_for_another_order_is_refused(self):
        other = self._order()
        issued = self.request_challenge(other)

        response = self.post_cancel(issued["digest"], self.sign(issued))

        self.assertEqual(response.status_code, 400, response.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, TransferOrderStatus.OPEN)

    def test_a_signature_from_another_key_is_refused(self):
        issued = self.request_challenge()

        response = self.post_cancel(issued["digest"], self.sign(issued, STRANGER))

        self.assertEqual(response.status_code, 403, response.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, TransferOrderStatus.OPEN)

    def test_an_expired_challenge_is_refused_and_says_so(self):
        issued = self.request_challenge()
        SigningChallenge.objects.filter(digest=issued["digest"]).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        response = self.post_cancel(issued["digest"], self.sign(issued))

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["code"], "challenge_expired")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, TransferOrderStatus.OPEN)

    def test_a_digest_nobody_issued_is_refused(self):
        response = self.post_cancel("0x" + "ee" * 32, "0x" + "ab" * 65)

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["code"], "challenge_unknown")

    def test_the_issued_challenge_names_the_chain_and_the_verifying_contract(self):
        issued = self.request_challenge()

        self.assertEqual(issued["domain"]["chainId"], settings.BLOCKCHAIN_CHAIN_ID)
        self.assertEqual(
            issued["domain"]["verifyingContract"],
            to_checksum_address(self.tenant.deployed_token.contract_address),
        )
        self.assertEqual(issued["message"]["orderUuid"], str(self.order.uuid))
        self.assertEqual(issued["message"]["wallet"], OWNER.address)
        self.assertIn("OrderCancel", issued["types"])

    def test_two_challenges_for_one_order_carry_different_nonces(self):
        first = self.request_challenge()
        second = self.request_challenge()

        self.assertNotEqual(first["digest"], second["digest"])
        self.assertNotEqual(first["message"]["nonce"], second["message"]["nonce"])

    def test_a_cancel_challenge_cannot_authorise_another_action(self):
        challenge = issue_challenge(
            SigningChallengePurpose.ORDER_CANCEL,
            OWNER.address,
            {"orderUuid": str(self.order.uuid)},
            verifying_contract=self.tenant.deployed_token.contract_address,
            order=self.order,
        )

        with self.assertRaises(ChallengeMismatchException):
            consume_challenge(
                challenge.digest,
                SigningChallengePurpose.ORDER_MODIFY,
                OWNER.address,
                "0x" + "ab" * 65,
            )

    def test_a_challenge_is_spendable_exactly_once_at_the_service_boundary(self):
        issued = self.request_challenge()
        signature = self.sign(issued)
        challenge = consume_challenge(
            issued["digest"], SigningChallengePurpose.ORDER_CANCEL, OWNER.address, signature, order=self.order
        )
        challenge.mark_consumed(signature)

        with self.assertRaises(ChallengeAlreadyUsedException):
            consume_challenge(
                issued["digest"], SigningChallengePurpose.ORDER_CANCEL, OWNER.address, signature, order=self.order
            )
