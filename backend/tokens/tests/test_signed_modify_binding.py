from uuid import uuid4

from django.db.models import ProtectedError
from django.test import TestCase
from rest_framework.test import APITransactionTestCase

from shared.utils.typed_data import recover_typed_data_signer
from tokens.models import (
    OrderModificationLog,
    SigningChallenge,
    SigningChallengePurpose,
)
from tokens.serializers.transfer_order import TransferOrderCreateSerializer
from tokens.services.signing_challenge import CHALLENGE_TYPES
from tokens.tests.order_action_fixtures import OTHER_KEY, OWNER, ActionFixtures

SERVER_ASSIGNED = {"wallet", "nonce", "deadline"}
NOT_SIGNED = {"wallet_address", "token"}


class ModifyChallengeCarriesEveryTermTest(ActionFixtures, APITransactionTestCase):
    def issue(self, **changes):
        context = self.context()
        self.assertEqual(context.status_code, 200, context.content)
        values = context.json()["currentValues"]
        body = self.modify_body(
            new_quantity=values["quantity"],
            new_min_quantity=values["minQuantity"],
            new_price_per_share=values["pricePerShare"],
        )
        body.update(changes)
        response = self.message("modify", body)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["challenge"]

    def test_untouched_context_values_are_named_in_what_the_caller_signs(self):
        issued = self.issue(new_quantity="12")
        self.assertEqual(issued["message"]["newQuantity"], "12")
        self.assertEqual(issued["message"]["newMinQuantity"], "0")
        self.assertEqual(issued["message"]["newPricePerShare"], "2.50")

    def test_every_term_of_the_order_is_in_the_signed_struct(self):
        struct = {field["name"] for field in CHALLENGE_TYPES[SigningChallengePurpose.ORDER_MODIFY]["OrderModifyV1"]}
        self.assertEqual(
            struct - SERVER_ASSIGNED,
            {
                "actionId",
                "protocolVersion",
                "ownerAccountUuid",
                "walletUuid",
                "tokenUuid",
                "orderUuid",
                "newQuantity",
                "newMinQuantity",
                "newPricePerShare",
            },
        )

    def test_the_challenge_is_bound_to_the_order_and_action_it_was_issued_for(self):
        issued = self.issue(new_quantity="12")
        challenge = SigningChallenge.objects.get(digest=issued["digest"])
        self.assertEqual(challenge.order_id, self.order.pk)
        self.assertEqual(challenge.action_id, self.journal().pk)
        self.assertEqual(challenge.purpose, SigningChallengePurpose.ORDER_MODIFY)

    def test_the_response_names_its_purpose_so_a_client_need_not_guess(self):
        self.assertEqual(self.issue(new_quantity="12")["purpose"], SigningChallengePurpose.ORDER_MODIFY)


class CreateChallengeCoversEveryFieldTheSerializerAcceptsTest(TestCase):

    def test_every_signable_create_field_appears_in_the_struct(self):
        struct = {field["name"] for field in CHALLENGE_TYPES[SigningChallengePurpose.ORDER_CREATE]["OrderCreate"]}
        signable = set(TransferOrderCreateSerializer().fields) - NOT_SIGNED
        camel = {"".join(p if i == 0 else p.title() for i, p in enumerate(name.split("_"))) for name in signable}

        self.assertEqual(camel - struct, set())


class TheAuditTrailNamesWhatWasSignedTest(ActionFixtures, APITransactionTestCase):
    def issue(self):
        response = self.message("modify", self.modify_body(new_min_quantity="0", new_price_per_share="2.50"))
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def apply(self, issued, signer=OWNER):
        return self.execute("modify", self.sign(issued, signer))

    def logged(self):
        return OrderModificationLog.objects.get(order=self.order, field_name="quantity")

    def test_the_address_in_the_log_is_the_one_that_signed_the_message(self):
        issued = self.issue()
        self.assertEqual(self.apply(issued).status_code, 200)
        log = self.logged()
        recovered = recover_typed_data_signer(
            log.challenge.payload["domain"],
            log.challenge.payload["types"],
            log.challenge.payload["message"],
            log.signature,
        )
        self.assertEqual(log.signer_address.lower(), recovered.lower())
        self.assertEqual(log.signer_address.lower(), OWNER.address.lower())
        self.assertNotEqual(
            recovered.lower(),
            recover_typed_data_signer(
                log.challenge.payload["domain"],
                log.challenge.payload["types"],
                log.challenge.payload["message"],
                self.sign(issued, OTHER_KEY)["signature"],
            ).lower(),
        )

    def test_a_signature_from_another_key_never_reaches_the_log(self):
        issued = self.issue()
        self.assertEqual(self.apply(issued, OTHER_KEY).status_code, 403)
        self.assertFalse(OrderModificationLog.objects.filter(order=self.order).exists())
        self.assertEqual(self.apply(issued).status_code, 200)
        self.assertTrue(OrderModificationLog.objects.filter(order=self.order).exists())

    def test_the_log_names_the_challenge_rather_than_carrying_a_bare_digest(self):
        issued = self.issue()
        self.assertEqual(self.apply(issued).status_code, 200)
        log = self.logged()
        self.assertEqual(log.challenge.digest, issued["challenge"]["digest"])
        self.assertEqual(log.challenge.payload["message"], issued["challenge"]["message"])
        self.assertEqual(log.modification_message, "")

    def test_the_challenge_a_log_names_cannot_be_deleted_out_from_under_it(self):
        issued = self.issue()
        self.assertEqual(self.apply(issued).status_code, 200)
        with self.assertRaises(ProtectedError):
            SigningChallenge.objects.get(digest=issued["challenge"]["digest"]).delete()
        self.action_id = uuid4()
        unreferenced = self.issue()
        SigningChallenge.objects.get(digest=unreferenced["challenge"]["digest"]).delete()
