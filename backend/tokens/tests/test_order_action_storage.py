from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from unittest import skipUnless
from uuid import uuid4

from django.db import IntegrityError, connection
from django.utils import timezone
from rest_framework.test import APITransactionTestCase

from shared.db import atomic, use_operator
from tokens.models import OrderActionSubmission, SigningChallenge
from tokens.services.signing_challenge import spend
from tokens.tests.order_action_fixtures import ActionFixtures


class OrderActionShapeTest(ActionFixtures, APITransactionTestCase):
    def test_the_same_account_cannot_allocate_a_second_row_for_an_action_id(self):
        self.signed()
        original = self.journal()
        values = {
            field.attname: getattr(original, field.attname)
            for field in original._meta.concrete_fields
            if field.name not in ("uuid", "created_at", "updated_at")
        }
        with use_operator(), self.assertRaises(IntegrityError), atomic():
            OrderActionSubmission.objects.create(**values)
        values["action_id"] = uuid4()
        with use_operator():
            second = OrderActionSubmission.objects.create(**values)
        self.assertNotEqual(second.pk, original.pk)

    def test_numeric_and_outcome_bounds_are_enforced_without_serializer_validation(self):
        self.signed("modify", self.modify_body())
        action = self.journal()
        for changes in (
            {"protocol_version": 2},
            {"chain_id": 0},
            {"new_quantity": 0},
            {"new_min_quantity": None},
            {"new_price_per_share": Decimal("0")},
            {"status": "applied"},
            {"status": "refused"},
            {"resolved_at": timezone.now()},
            {"purpose": "bad"},
            {"refusal_code": "database_unavailable"},
        ):
            with self.subTest(changes=changes), use_operator(), self.assertRaises(IntegrityError), atomic():
                OrderActionSubmission.objects.filter(pk=action.pk).update(**changes)
        self.assertEqual(self.journal().status, "pending")
        self.assertEqual(self.execute("modify", self.signed("modify", self.modify_body())).status_code, 200)


@skipUnless(connection.vendor == "postgresql", "PostgreSQL enforces action history and linked challenge guards")
class OrderActionHistoryTest(ActionFixtures, APITransactionTestCase):
    def test_original_identity_domain_terms_and_display_cannot_be_rewritten_or_deleted(self):
        signed = self.signed("modify", self.modify_body())
        original = self.journal()
        for changes in (
            {"action_id": uuid4()},
            {"order_id": self.tenant.order.pk},
            {"wallet_id": self.tenant.wallet.pk},
            {"token_id": self.tenant.token.pk},
            {"wallet_address": self.tenant.wallet.address},
            {"chain_id": original.chain_id + 1},
            {"verifying_contract": "0x" + "99" * 20},
            {"new_quantity": 13},
            {"new_min_quantity": 2},
            {"new_price_per_share": Decimal("3.01")},
            {"token_metadata": {"name": "Changed", "symbol": "ALT"}},
            {"review_values": {**original.review_values, "quantity": "9"}},
            {"created_at": original.created_at - timedelta(days=1)},
        ):
            with self.subTest(changes=changes), use_operator(), self.assertRaises(IntegrityError), atomic():
                OrderActionSubmission.objects.filter(pk=original.pk).update(**changes)
        with use_operator(), self.assertRaises(IntegrityError), atomic(), connection.cursor() as cursor:
            cursor.execute("DELETE FROM tokens_orderactionsubmission WHERE uuid = %s", [original.pk])
        self.assertEqual(self.execute("modify", signed).status_code, 200)

    def test_a_resolution_requires_its_own_spent_challenge(self):
        signed = self.signed()
        own = self.journal()
        other_signed = self.signed(body=self.identity(action_id=str(uuid4())))
        with use_operator():
            own_challenge = SigningChallenge.objects.get(digest=signed["digest"])
            other_challenge = SigningChallenge.objects.get(digest=other_signed["digest"])
            spend(other_challenge, other_signed["signature"])
            for challenge in (own_challenge, other_challenge):
                with self.subTest(challenge=challenge.pk), self.assertRaises(IntegrityError), atomic():
                    OrderActionSubmission.objects.filter(pk=own.pk).update(
                        status="refused",
                        executed_challenge=challenge,
                        executed_by=self.tenant.user,
                        resolved_at=timezone.now(),
                        refusal_code="order_cancellation_failed",
                        refusal_detail="Order cannot be cancelled.",
                        refusal_status=400,
                    )
        self.assertEqual(self.execute("cancel", signed).status_code, 200)

    def test_an_applied_result_cannot_be_inserted_without_the_local_mutation(self):
        signed = self.signed("modify", self.modify_body())
        action = self.journal()
        with use_operator():
            challenge = SigningChallenge.objects.get(digest=signed["digest"])
            spend(challenge, signed["signature"])
            with self.assertRaises(IntegrityError), atomic():
                OrderActionSubmission.objects.filter(pk=action.pk).update(
                    status="applied",
                    executed_challenge=challenge,
                    executed_by=self.tenant.user,
                    resolved_at=timezone.now(),
                    result={"kind": "modify", "modification_count": 0, "changes": []},
                )
            self.order.refresh_from_db()
        self.assertEqual(self.order.quantity, 10)
        self.assertEqual(self.journal().status, "pending")
        refreshed = self.signed("modify", self.modify_body())
        self.assertEqual(self.execute("modify", refreshed).status_code, 200)

    def test_terminal_outcome_and_refusal_discriminators_cannot_be_rewritten(self):
        signed = self.signed()
        response = self.execute("cancel", signed)
        self.assertEqual(response.status_code, 200, response.content)
        original = self.journal()
        for changes in (
            {"result": {"kind": "cancel", "from_status": "partially_filled", "to_status": "cancelled"}},
            {"resolved_at": original.resolved_at + timedelta(seconds=1)},
            {"status": "pending", "result": None, "executed_challenge": None, "executed_by": None, "resolved_at": None},
            {
                "status": "refused",
                "result": None,
                "refusal_code": "order_cancellation_failed",
                "refusal_detail": "Changed",
                "refusal_status": 400,
            },
        ):
            with self.subTest(changes=changes), use_operator(), self.assertRaises(IntegrityError), atomic():
                OrderActionSubmission.objects.filter(pk=original.pk).update(**changes)
        self.assertEqual(self.recover().json(), response.json())

    def test_new_challenges_cannot_substitute_any_action_identity_domain_or_terms(self):
        signed = self.signed("modify", self.modify_body())
        with use_operator():
            issued = SigningChallenge.objects.get(digest=signed["digest"])
        values = {
            field.attname: getattr(issued, field.attname)
            for field in issued._meta.concrete_fields
            if field.name not in ("uuid", "created_at", "updated_at")
        }
        for field, value in {
            "actionId": str(uuid4()),
            "ownerAccountUuid": str(uuid4()),
            "walletUuid": str(uuid4()),
            "tokenUuid": str(uuid4()),
            "orderUuid": str(uuid4()),
            "protocolVersion": "2",
            "newQuantity": "13",
            "newMinQuantity": "2",
            "newPricePerShare": "3.01",
        }.items():
            changed = deepcopy(values)
            changed["nonce"] += 1
            changed["digest"] = "0x" + "ac" * 32
            changed["payload"]["message"]["nonce"] = str(changed["nonce"])
            changed["payload"]["message"][field] = value
            with self.subTest(field=field), use_operator(), self.assertRaises(IntegrityError), atomic():
                SigningChallenge.objects.create(**changed)
        valid = deepcopy(values)
        valid["nonce"] += 1
        valid["digest"] = "0x" + "ac" * 32
        valid["payload"]["message"]["nonce"] = str(valid["nonce"])
        with use_operator():
            control = SigningChallenge.objects.create(**valid)
        self.assertIsNotNone(control.pk)
        self.assertEqual(self.execute("modify", signed).status_code, 200)

    def test_an_existing_challenge_cannot_be_linked_to_a_second_action(self):
        first = self.signed()
        second = self.signed(body=self.identity(action_id=str(uuid4())))
        with use_operator():
            other = SigningChallenge.objects.get(digest=second["digest"])
            with self.assertRaises(IntegrityError), atomic():
                SigningChallenge.objects.filter(digest=first["digest"]).update(action=other.action)
        self.assertEqual(self.execute("cancel", first).status_code, 200)
