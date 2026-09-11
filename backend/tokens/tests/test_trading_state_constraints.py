from datetime import timedelta
from decimal import Decimal
from unittest import skipUnless
from uuid import uuid4

from django.db import IntegrityError, connection
from django.test import TestCase
from django.utils import timezone

from shared.db import atomic
from shared.tests.tenants import make_tenant
from tokens.models import (
    SigningChallenge,
    SigningChallengePurpose,
    SwapOrder,
    TransferOrder,
)
from tokens.models.choices import SwapOrderStatus, TransferOrderStatus
from tokens.services.signing_challenge import (
    issue_challenge,
    purge_expired_challenges,
    spend,
)
from tokens.tests.signing_challenge_fixtures import action_fields, pending_action


class TradingAmountsAndStatesAreDatabaseRulesTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("bounds")
        self.order = self.tenant.swap.sell_order

    def test_raw_order_updates_cannot_create_invalid_amounts_or_states(self):
        for changes in (
            {"quantity": 0},
            {"price_per_share": Decimal("0")},
            {"price_per_share": Decimal("-0.01")},
            {"filled_quantity": self.order.quantity + 1},
            {"min_quantity": self.order.quantity + 1},
            {"status": "invented"},
            {"order_type": "invented"},
        ):
            with self.subTest(changes=changes), self.assertRaises(IntegrityError), atomic():
                TransferOrder.objects.filter(pk=self.order.pk).update(**changes)

    def test_raw_swap_updates_cannot_create_invalid_amounts_or_states(self):
        for changes in ({"share_amount": 0}, {"payment_amount": 0}, {"status": "invented"}):
            with self.subTest(changes=changes), self.assertRaises(IntegrityError), atomic():
                SwapOrder.objects.filter(pk=self.tenant.swap.pk).update(**changes)

    def test_bulk_insert_and_model_save_cannot_bypass_the_bounds(self):
        self.order.quantity = 0
        with self.assertRaises(IntegrityError), atomic():
            self.order.save(update_fields=["quantity"])

        values = TransferOrder.objects.filter(pk=self.order.pk).values().get()
        values.update(uuid=uuid4(), min_quantity=values["quantity"] + 1)
        with self.assertRaises(IntegrityError), atomic():
            TransferOrder.objects.bulk_create([TransferOrder(**values)])

    def test_valid_partial_history_and_all_existing_status_values_survive(self):
        for status in TransferOrderStatus.values:
            TransferOrder.objects.filter(pk=self.order.pk).update(
                quantity=10, filled_quantity=8, min_quantity=9, price_per_share=Decimal("0.01"), status=status
            )
            self.order.refresh_from_db()
            self.assertEqual((self.order.filled_quantity, self.order.min_quantity), (8, 9))
        for status in SwapOrderStatus.values:
            SwapOrder.objects.filter(pk=self.tenant.swap.pk).update(status=status, nonce=0)
            self.tenant.swap.refresh_from_db()
            self.assertEqual((self.tenant.swap.status, self.tenant.swap.nonce), (status, 0))


@skipUnless(connection.vendor == "postgresql", "PostgreSQL numeric NaN needs a raw PostgreSQL write")
class PostgreSQLPricesRemainFiniteTest(TestCase):

    def test_raw_numeric_nan_is_refused_while_the_maximum_positive_price_is_preserved(self):
        order = make_tenant("finite-price").order
        maximum = Decimal("9999999999999999.99")
        TransferOrder.objects.filter(pk=order.pk).update(price_per_share=maximum)
        order.refresh_from_db()
        self.assertEqual(order.price_per_share, maximum)
        with self.assertRaises(IntegrityError), atomic(), connection.cursor() as cursor:
            cursor.execute(
                "UPDATE tokens_transferorder SET price_per_share = 'NaN'::numeric WHERE uuid = %s", [order.pk]
            )
        order.refresh_from_db()
        self.assertEqual(order.price_per_share, maximum)


class ChallengeSpendingHasTwoConsistentFieldsTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("challenge-bounds")
        action = pending_action(self.tenant, order=self.tenant.swap.sell_order)
        self.challenge = issue_challenge(
            SigningChallengePurpose.ORDER_CANCEL,
            self.tenant.wallet.address,
            action_fields(action),
            verifying_contract=action.verifying_contract,
            order=self.tenant.swap.sell_order,
            action=action,
        )

    def test_neither_half_of_a_spend_can_be_written_alone(self):
        for changes in ({"consumed_at": timezone.now()}, {"consumed_signature": "signed"}):
            with self.subTest(changes=changes), self.assertRaises(IntegrityError), atomic():
                SigningChallenge.objects.filter(pk=self.challenge.pk).update(**changes)

    def test_normal_issue_and_spend_preserve_the_issued_intent(self):
        before = self.challenge.payload
        spend(self.challenge, "signed")
        self.challenge.refresh_from_db()
        self.assertIsNotNone(self.challenge.consumed_at)
        self.assertEqual(self.challenge.consumed_signature, "signed")
        self.assertEqual(self.challenge.payload, before)


@skipUnless(connection.vendor == "postgresql", "issued-intent protection is a PostgreSQL trigger")
class IssuedChallengeIntentCannotBeRewrittenTest(ChallengeSpendingHasTwoConsistentFieldsTest):

    def test_resetting_both_spend_fields_cannot_make_a_challenge_reusable(self):
        spend(self.challenge, "signed")
        with self.assertRaises(IntegrityError), atomic():
            SigningChallenge.objects.filter(pk=self.challenge.pk).update(consumed_at=None, consumed_signature="")
        self.challenge.refresh_from_db()
        self.assertTrue(self.challenge.is_consumed)
        self.assertEqual(self.challenge.consumed_signature, "signed")

    def test_a_payload_rewrite_is_refused_without_changing_any_existing_owner_column(self):
        with self.assertRaises(IntegrityError), atomic():
            SigningChallenge.objects.filter(pk=self.challenge.pk).update(payload={"message": {"orderUuid": "other"}})
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.payload["message"]["orderUuid"], str(self.tenant.swap.sell_order_id))

    def test_every_issued_intent_field_is_immutable_through_raw_updates(self):
        for changes in (
            {"purpose": SigningChallengePurpose.ORDER_CREATE},
            {"wallet_address": "0x" + "ab" * 20},
            {"order_id": None},
            {"wallet_id": None},
            {"chain_id": 1},
            {"verifying_contract": "0x" + "cd" * 20},
            {"nonce": self.challenge.nonce + 1},
            {"digest": "0x" + "ef" * 32},
            {"payload": {"message": {"orderUuid": "different"}}},
            {"expires_at": self.challenge.expires_at + timedelta(days=1)},
            {"created_at": self.challenge.created_at - timedelta(days=1)},
            {"uuid": uuid4()},
        ):
            with self.subTest(changes=changes), self.assertRaises(IntegrityError), atomic():
                SigningChallenge.objects.filter(pk=self.challenge.pk).update(**changes)

    def test_a_spent_time_or_signature_cannot_be_replaced_through_model_save(self):
        spend(self.challenge, "signed")
        for changes in (
            {"consumed_at": self.challenge.consumed_at + timedelta(seconds=1)},
            {"consumed_signature": "different"},
        ):
            self.challenge.refresh_from_db()
            for name, value in changes.items():
                setattr(self.challenge, name, value)
            with self.subTest(changes=changes), self.assertRaises(IntegrityError), atomic():
                self.challenge.save(update_fields=list(changes))

    def test_bookkeeping_updates_and_existing_unspent_purge_are_still_allowed(self):
        SigningChallenge.objects.filter(pk=self.challenge.pk).update(updated_at=timezone.now())
        self.assertTrue(SigningChallenge.objects.filter(pk=self.challenge.pk).exists())
        removed = purge_expired_challenges(now=self.challenge.expires_at + timedelta(days=365))
        self.assertEqual(removed, 1)
        self.assertFalse(SigningChallenge.objects.filter(pk=self.challenge.pk).exists())
