from decimal import Decimal
from unittest.mock import patch

from django.db.models import ProtectedError
from django.test import TestCase
from eth_account import Account

from shared.tests.tenants import make_tenant
from shared.utils.typed_data import recover_typed_data_signer, signable_message
from tokens.exceptions import InvalidSignatureException
from tokens.models import (
    OrderModificationLog,
    SigningChallenge,
    SigningChallengePurpose,
    TransferOrder,
)
from tokens.models.choices import TransferOrderType
from tokens.serializers.transfer_order import TransferOrderCreateSerializer
from tokens.services import OrderModificationService
from tokens.services.signing_challenge import CHALLENGE_TYPES
from wallets.models import Wallet

WALLET = "0x" + "c4" * 20
OWNER = Account.from_key("0x" + "5b" * 32)
STRANGER = Account.from_key("0x" + "7e" * 32)
SERVER_ASSIGNED = {"wallet", "nonce", "deadline"}
NOT_SIGNED = {"wallet_address", "token"}


class ModifyChallengeCarriesEveryTermTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("modifier")
        wallet = Wallet.objects.create(
            user_account=self.tenant.account, address=WALLET, chain="base", verification_status="VERIFIED"
        )
        self.order = TransferOrder.objects.create(
            order_type=TransferOrderType.BUY,
            token=self.tenant.deployed_token,
            payment_asset=self.tenant.refs.stablecoin,
            wallet=wallet,
            owner_account=self.tenant.account,
            wallet_address=WALLET,
            quantity=10,
            min_quantity=2,
            price_per_share=Decimal("1.50"),
        )

    def issue(self, **changes):
        return OrderModificationService().generate_modification_message(order=self.order, **changes)

    def test_a_term_the_caller_omits_is_still_named_in_what_they_sign(self):
        issued = self.issue(new_quantity=12)

        self.assertEqual(issued["message"]["newQuantity"], "12")
        self.assertEqual(issued["message"]["newMinQuantity"], "2")
        self.assertEqual(issued["message"]["newPricePerShare"], "1.50")

    def test_every_term_of_the_order_is_in_the_signed_struct(self):
        struct = {field["name"] for field in CHALLENGE_TYPES[SigningChallengePurpose.ORDER_MODIFY]["OrderModify"]}

        self.assertEqual(struct - SERVER_ASSIGNED, {"orderUuid", "newQuantity", "newMinQuantity", "newPricePerShare"})

    def test_the_challenge_is_bound_to_the_order_it_was_issued_for(self):
        issued = self.issue(new_quantity=12)
        challenge = SigningChallenge.objects.get(digest=issued["digest"])

        self.assertEqual(challenge.order_id, self.order.pk)
        self.assertEqual(challenge.purpose, SigningChallengePurpose.ORDER_MODIFY)

    def test_the_response_names_its_purpose_so_a_client_need_not_guess(self):
        self.assertEqual(self.issue(new_quantity=12)["purpose"], SigningChallengePurpose.ORDER_MODIFY)


class CreateChallengeCoversEveryFieldTheSerializerAcceptsTest(TestCase):

    def test_every_signable_create_field_appears_in_the_struct(self):
        struct = {field["name"] for field in CHALLENGE_TYPES[SigningChallengePurpose.ORDER_CREATE]["OrderCreate"]}
        signable = set(TransferOrderCreateSerializer().fields) - NOT_SIGNED
        camel = {"".join(p if i == 0 else p.title() for i, p in enumerate(name.split("_"))) for name in signable}

        self.assertEqual(camel - struct, set())


class TheAuditTrailNamesWhatWasSignedTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("auditor")
        wallet = Wallet.objects.create(
            user_account=self.tenant.account, address=OWNER.address, chain="base", verification_status="VERIFIED"
        )
        self.order = TransferOrder.objects.create(
            order_type=TransferOrderType.BUY,
            token=self.tenant.deployed_token,
            payment_asset=self.tenant.refs.stablecoin,
            wallet=wallet,
            owner_account=self.tenant.account,
            wallet_address=OWNER.address,
            quantity=10,
            min_quantity=0,
            price_per_share=Decimal("1.50"),
        )

    def issue(self):
        return OrderModificationService().generate_modification_message(order=self.order, new_quantity=12)

    @staticmethod
    def sign(issued, account=OWNER):
        return account.sign_message(
            signable_message(issued["domain"], issued["types"], issued["message"])
        ).signature.hex()

    @patch("tokens.events.publish_trading_event")
    def apply(self, issued, signature, _publish):
        return OrderModificationService().apply_modification(
            order=self.order, digest=issued["digest"], signature=signature
        )

    def logged(self):
        return OrderModificationLog.objects.get(order=self.order, field_name="quantity")

    def test_the_address_in_the_log_is_the_one_that_signed_the_message(self):
        issued = self.issue()
        self.apply(issued, self.sign(issued))

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
                self.sign(issued, STRANGER),
            ).lower(),
        )

    def test_a_signature_from_another_key_never_reaches_the_log(self):
        issued = self.issue()

        with self.assertRaises(InvalidSignatureException):
            self.apply(issued, self.sign(issued, STRANGER))

        self.assertFalse(OrderModificationLog.objects.filter(order=self.order).exists())

    def test_the_log_names_the_challenge_rather_than_carrying_a_bare_digest(self):
        issued = self.issue()
        self.apply(issued, self.sign(issued))

        log = self.logged()

        self.assertEqual(log.challenge.digest, issued["digest"])
        self.assertEqual(log.challenge.payload["message"], issued["message"])
        self.assertEqual(log.modification_message, "")

    def test_the_challenge_a_log_names_cannot_be_deleted_out_from_under_it(self):
        issued = self.issue()
        self.apply(issued, self.sign(issued))

        with self.assertRaises(ProtectedError):
            SigningChallenge.objects.get(digest=issued["digest"]).delete()

        unreferenced = self.issue()
        SigningChallenge.objects.get(digest=unreferenced["digest"]).delete()
