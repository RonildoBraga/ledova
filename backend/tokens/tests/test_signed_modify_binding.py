from decimal import Decimal

from django.test import TestCase

from shared.tests.tenants import make_tenant
from tokens.models import SigningChallenge, SigningChallengePurpose, TransferOrder
from tokens.models.choices import TransferOrderType
from tokens.serializers.transfer_order import TransferOrderCreateSerializer
from tokens.services import OrderModificationService
from tokens.services.signing_challenge import CHALLENGE_TYPES
from wallets.models import Wallet

WALLET = "0x" + "c4" * 20
SERVER_ASSIGNED = {"wallet", "nonce", "deadline"}
NOT_SIGNED = {"wallet_uuid", "wallet_address", "token"}


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
