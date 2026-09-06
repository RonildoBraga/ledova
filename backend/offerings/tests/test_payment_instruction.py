from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from assets.models import AssetChainDeployment
from offerings.exceptions import SubscriptionRefusedException
from offerings.models import (
    MAX_REFERENCE_LENGTH,
    SettlementRail,
    Subscription,
    SubscriptionStatus,
)
from offerings.services.payments import (
    BANK_NOT_CONFIGURED,
    CROCKFORD_ALPHABET,
    NO_REFERENCE_PREFIX,
    REFERENCE_CODE_LENGTH,
    WALLET_NOT_CONFIGURED,
    build_instruction,
    generate_reference,
    normalize_reference,
)
from offerings.services.subscription import accept, issue_instruction, submit
from offerings.tests.factories import (
    configure_operator,
    draft_subscription,
    eligible_subscriber,
    open_offering,
)
from operators.exceptions import SettlementAssetNotDeployedException
from operators.models import Operator
from operators.settlement import NOT_DEPLOYED
from shared.tests.tenants import make_tenant


class NormalizeReferenceTest(TestCase):
    def test_a_mangled_bank_narrative_normalizes_onto_the_stored_reference(self):
        self.assertEqual(normalize_reference("pay 4h7k-9m2n"), "PAY4H7K9M2N")
        self.assertEqual(normalize_reference("PAY/4H7K 9M2N"), "PAY4H7K9M2N")
        self.assertEqual(normalize_reference("  pay4h7k9m2n  "), "PAY4H7K9M2N")

    def test_the_confusable_letters_collapse_the_way_crockford_reads_them(self):
        self.assertEqual(normalize_reference("LED0VA"), "1ED0VA")
        self.assertEqual(normalize_reference("O1IL"), "0111")
        self.assertEqual(normalize_reference(""), "")
        self.assertEqual(normalize_reference(None), "")

    def test_the_generated_alphabet_carries_no_confusable_letter(self):
        for letter in "ILOU":
            self.assertNotIn(letter, CROCKFORD_ALPHABET)


class GenerateReferenceTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant("refs")
        configure_operator()
        self.operator = Operator.get()

    def test_the_reference_is_the_prefix_plus_an_eight_character_code(self):
        reference = generate_reference(self.operator)
        self.assertTrue(reference.startswith("PAY"), reference)
        self.assertEqual(len(reference), 3 + REFERENCE_CODE_LENGTH)
        self.assertLessEqual(len(reference), MAX_REFERENCE_LENGTH)
        self.assertEqual(normalize_reference(reference), reference)

    def test_the_prefix_is_normalized_at_generation_so_a_lookup_can_match_it(self):
        configure_operator(payment_reference_prefix="LEDOVA")
        reference = generate_reference(Operator.get())
        self.assertTrue(reference.startswith("1ED0VA"), reference)
        self.assertEqual(normalize_reference(reference), reference)

    def test_a_long_prefix_still_fits_the_lodgement_limit(self):
        configure_operator(payment_reference_prefix="ABCDEFGHJK")
        self.assertEqual(len(generate_reference(Operator.get())), MAX_REFERENCE_LENGTH)

    def test_no_prefix_refuses_rather_than_issuing_a_bare_code(self):
        Operator.objects.update(payment_reference_prefix="")
        with self.assertRaises(SubscriptionRefusedException) as raised:
            generate_reference(Operator.get())
        self.assertEqual(str(raised.exception.detail), NO_REFERENCE_PREFIX)

    def test_a_thousand_references_are_all_distinct(self):
        references = {generate_reference(self.operator) for _ in range(1000)}
        self.assertEqual(len(references), 1000)


class IssueInstructionTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant("payer")
        self.stablecoin = self.tenant.refs.stablecoin
        configure_operator(stablecoin=self.stablecoin)
        self.offering = open_offering(self.tenant, stablecoin=self.stablecoin)
        eligible_subscriber(self.tenant)

    def _accepted(self):
        subscription = draft_subscription(self.tenant)
        submit(subscription, submitted_by=self.tenant.user)
        accept(subscription)
        return subscription

    def test_a_colliding_code_is_retried_until_it_lands(self):
        taken = self._accepted()
        issue_instruction(taken, rail=SettlementRail.BANK_TRANSFER)
        collision = taken.reference[3:]

        codes = iter([collision, collision, "ZZZZZZZZ"])
        second = self._accepted()
        with patch("offerings.services.payments._code", side_effect=lambda: next(codes)):
            issue_instruction(second, rail=SettlementRail.BANK_TRANSFER)

        second.refresh_from_db()
        self.assertEqual(second.reference, "PAYZZZZZZZZ")
        self.assertEqual(Subscription.objects.filter(reference=taken.reference).count(), 1)

    def test_a_reference_that_slips_past_the_precheck_is_retried_on_the_integrity_error(self):
        taken = self._accepted()
        issue_instruction(taken, rail=SettlementRail.BANK_TRANSFER)

        second = self._accepted()
        with patch(
            "offerings.services.subscription.generate_reference",
            side_effect=[taken.reference, "PAYFRESH01"],
        ) as generator:
            issue_instruction(second, rail=SettlementRail.BANK_TRANSFER)

        self.assertEqual(generator.call_count, 2)
        second.refresh_from_db()
        self.assertEqual(second.reference, "PAYFRESH01")
        self.assertEqual(second.status, SubscriptionStatus.AWAITING_PAYMENT)
        self.assertEqual(Subscription.objects.filter(reference=taken.reference).count(), 1)

    def test_the_bank_instruction_carries_the_operator_rails_and_the_exact_amount(self):
        subscription = self._accepted()
        issue_instruction(subscription, rail=SettlementRail.BANK_TRANSFER)
        instruction = build_instruction(subscription)

        self.assertEqual(instruction["rail"], SettlementRail.BANK_TRANSFER)
        self.assertEqual(instruction["bank_account_name"], "Ledova Trust Account")
        self.assertEqual(instruction["bank_bsb"], "062000")
        self.assertEqual(instruction["bank_account_number"], "12345678")
        self.assertEqual(instruction["amount_due"], "25.00")
        self.assertEqual(instruction["currency"], "AUD")
        self.assertEqual(instruction["reference"], subscription.reference)

    def test_the_stablecoin_instruction_carries_the_wallet_contract_and_decimals(self):
        subscription = self._accepted()
        issue_instruction(subscription, rail=SettlementRail.STABLECOIN, settlement_asset=self.stablecoin)
        instruction = build_instruction(subscription)

        self.assertEqual(instruction["rail"], SettlementRail.STABLECOIN)
        self.assertEqual(instruction["receiving_wallet_address"], "0x" + "d" * 40)
        self.assertEqual(instruction["chain"], "base")
        self.assertEqual(instruction["asset_symbol"], "TUSD")
        self.assertEqual(instruction["contract_address"], "0x" + "5" * 40)
        self.assertEqual(instruction["decimals"], 2)
        self.assertEqual(instruction["settlement_amount"], "2500")

    def test_the_instruction_refuses_when_the_settlement_asset_has_no_deployment_on_the_chain(self):
        AssetChainDeployment.objects.filter(asset=self.stablecoin, chain="base").update(is_active=False)
        subscription = self._accepted()
        with self.assertRaises(SettlementAssetNotDeployedException) as raised:
            issue_instruction(subscription, rail=SettlementRail.STABLECOIN, settlement_asset=self.stablecoin)
        self.assertEqual(str(raised.exception.detail), NOT_DEPLOYED.format(symbol="TUSD", chain="base"))

    def test_the_instruction_refuses_when_the_receiving_chain_moves_away_from_the_deployment(self):
        configure_operator(stablecoin=self.stablecoin, receiving_wallet_chain="ethereum")
        subscription = self._accepted()
        with self.assertRaises(SettlementAssetNotDeployedException) as raised:
            issue_instruction(subscription, rail=SettlementRail.STABLECOIN, settlement_asset=self.stablecoin)
        self.assertEqual(str(raised.exception.detail), NOT_DEPLOYED.format(symbol="TUSD", chain="ethereum"))

    def test_a_bank_instruction_refuses_without_bank_details(self):
        subscription = self._accepted()
        issue_instruction(subscription, rail=SettlementRail.BANK_TRANSFER)
        Operator.objects.update(bank_account_number="")
        with self.assertRaises(SubscriptionRefusedException) as raised:
            build_instruction(subscription)
        self.assertEqual(str(raised.exception.detail), BANK_NOT_CONFIGURED)

    def test_a_stablecoin_instruction_refuses_without_a_receiving_wallet(self):
        subscription = self._accepted()
        issue_instruction(subscription, rail=SettlementRail.STABLECOIN, settlement_asset=self.stablecoin)
        Operator.objects.update(receiving_wallet_address="")
        with self.assertRaises(SubscriptionRefusedException) as raised:
            build_instruction(subscription)
        self.assertEqual(str(raised.exception.detail), WALLET_NOT_CONFIGURED)

    def test_a_price_finer_than_the_settlement_asset_is_refused_rather_than_rounded(self):
        AssetChainDeployment.objects.filter(asset=self.stablecoin, chain="base").update(decimals=0)
        self.offering.price_per_share = Decimal("2.55")
        self.offering.save(update_fields=["price_per_share"])
        subscription = self._accepted()
        self.assertEqual(subscription.amount_due, Decimal("25.50"))
        with self.assertRaises(SubscriptionRefusedException) as raised:
            issue_instruction(subscription, rail=SettlementRail.STABLECOIN, settlement_asset=self.stablecoin)
        self.assertIn("cannot be expressed in whole units of TUSD", str(raised.exception.detail))
