from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from unittest import skipUnless
from uuid import uuid4

from django.db import IntegrityError, connection
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITransactionTestCase

from shared.db import atomic, use_operator
from shared.tests.tenants import make_tenant
from tokens.models import OrderSubmission, SigningChallenge, TransferOrder
from tokens.services.signing_challenge import spend
from tokens.tests.order_submission_fixtures import (
    SubmissionFixtures,
    pending_submission,
)


class OrderSubmissionShapeTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant("submission-shape")
        self.submission = pending_submission(self.tenant)

    def test_account_and_key_are_unique_while_another_account_can_reuse_the_uuid(self):
        with self.assertRaises(IntegrityError), atomic():
            pending_submission(self.tenant, submission_id=self.submission.submission_id)
        other = make_tenant("submission-shape-other")
        distinct = pending_submission(other, submission_id=self.submission.submission_id)
        self.assertNotEqual(distinct.pk, self.submission.pk)

    def test_numeric_bounds_and_outcome_shape_cannot_be_bypassed(self):
        for changes in (
            {"quantity": 0},
            {"quantity": 1, "min_quantity": 2},
            {"price_per_share": Decimal("0")},
            {"intent_version": 2},
            {"order_type": "unknown"},
            {"status": "created"},
            {"status": "refused", "refusal_code": "database_unavailable"},
            {"resolved_at": timezone.now()},
            {"order": self.tenant.order},
            {"initial_swap": self.tenant.swap},
        ):
            with self.subTest(changes=changes), self.assertRaises(IntegrityError), atomic():
                OrderSubmission.objects.filter(pk=self.submission.pk).update(**changes)
        self.submission.refresh_from_db()
        self.assertEqual((self.submission.status, self.submission.quantity), ("pending", 10))


@skipUnless(connection.vendor == "postgresql", "PostgreSQL protects immutable submission history")
class OrderSubmissionHistoryTest(SubmissionFixtures, APITransactionTestCase):
    def test_all_original_identity_and_display_fields_are_immutable_and_keys_cannot_be_deleted(self):
        self.issue()
        original = self.submission()
        for changes in (
            {"uuid": uuid4()},
            {"submission_id": uuid4()},
            {"wallet_id": self.tenant.wallet.pk},
            {"owner_account_id": uuid4()},
            {"token_id": self.tenant.token.pk},
            {"initiated_by_id": 99999999},
            {"wallet_address": self.tenant.wallet.address},
            {"order_type": "sell"},
            {"quantity": 11},
            {"min_quantity": 1},
            {"price_per_share": Decimal("2.51")},
            {"chain_id": original.chain_id + 1},
            {"verifying_contract": "0x" + "ab" * 20},
            {"token_metadata": {"name": "changed", "symbol": "NEW"}},
            {"created_at": original.created_at - timedelta(days=1)},
        ):
            with self.subTest(changes=changes), use_operator(), self.assertRaises(IntegrityError), atomic():
                OrderSubmission.objects.filter(pk=original.pk).update(**changes)
        with self.assertRaises(IntegrityError), atomic(), connection.cursor() as cursor:
            cursor.execute("DELETE FROM tokens_ordersubmission WHERE uuid = %s", [original.pk])
        self.assertEqual(self.submission().submission_id, self.submission_id)

    def test_resolution_requires_its_own_spent_challenge(self):
        signed = self.signed_body()
        second = self.signed_body(self.body(submission_id=str(uuid4())))
        with use_operator():
            own = SigningChallenge.objects.get(digest=signed["digest"])
            other = SigningChallenge.objects.get(digest=second["digest"])
            spend(other, second["signature"])
            for challenge in (own, other):
                with self.subTest(challenge=challenge.pk), self.assertRaises(IntegrityError), atomic():
                    OrderSubmission.objects.filter(pk=self.submission().pk).update(
                        status="refused",
                        executed_challenge=challenge,
                        resolved_at=timezone.now(),
                        refusal_code="not_whitelisted",
                        refusal_detail="Address is not whitelisted.",
                    )
        self.assertEqual(self.create(signed).status_code, 201)

    def test_terminal_history_cannot_be_reopened_or_repointed(self):
        signed = self.signed_body()
        created = self.create(signed)
        self.assertEqual(created.status_code, 201, created.content)
        original = self.submission()
        for changes in (
            {"order": self.tenant.order},
            {"executed_challenge_id": uuid4()},
            {"resolved_at": original.resolved_at + timedelta(seconds=1)},
            {"status": "pending", "order": None, "executed_challenge": None, "resolved_at": None},
        ):
            with self.subTest(changes=changes), use_operator(), self.assertRaises(IntegrityError), atomic():
                OrderSubmission.objects.filter(pk=original.pk).update(**changes)
        self.assertEqual(self.recover().json(), created.json())
        self.submission_id = uuid4()
        self.whitelist.is_whitelisted.return_value = False
        refused = self.create(self.signed_body())
        self.assertEqual(refused.status_code, 400)
        with use_operator(), self.assertRaises(IntegrityError), atomic():
            OrderSubmission.objects.filter(pk=self.submission().pk).update(refusal_detail="A different refusal")
        self.assertEqual(self.recover().json(), refused.json())

    def test_challenge_linkage_cannot_be_removed_reassigned_or_retrofitted(self):
        issued = self.issue()
        original = self.submission()
        with use_operator():
            challenge = SigningChallenge.objects.get(digest=issued["digest"])
            for link in (None, uuid4()):
                with self.subTest(link=link), self.assertRaises(IntegrityError), atomic():
                    SigningChallenge.objects.filter(pk=challenge.pk).update(submission_id=link)
            values = SigningChallenge.objects.filter(pk=challenge.pk).values().get()
            values.update(uuid=uuid4(), submission_id=None, nonce=challenge.nonce + 1, digest="0x" + "cd" * 32)
            legacy = SigningChallenge.objects.create(**values)
            with self.assertRaises(IntegrityError), atomic():
                SigningChallenge.objects.filter(pk=legacy.pk).update(submission=original)
            legacy.refresh_from_db()
            self.assertIsNone(legacy.submission_id)

    def test_a_new_challenge_cannot_bind_different_semantic_terms(self):
        issued = self.issue()
        with use_operator():
            challenge = SigningChallenge.objects.get(digest=issued["digest"])
            for key, changed in (
                ("submissionId", str(uuid4())),
                ("ownerAccountUuid", str(uuid4())),
                ("walletUuid", str(uuid4())),
                ("quantity", "11"),
                ("pricePerShare", "3.00"),
            ):
                values = SigningChallenge.objects.filter(pk=challenge.pk).values().get()
                values.update(uuid=uuid4(), nonce=challenge.nonce + 1, digest="0x" + "ed" * 32)
                values["payload"] = deepcopy(values["payload"])
                values["payload"]["message"][key] = changed
                with self.subTest(key=key), self.assertRaises(IntegrityError), atomic():
                    SigningChallenge.objects.create(**values)

    def test_resolution_cannot_attach_an_unrelated_order_or_match(self):
        signed = self.signed_body()
        with use_operator():
            challenge = SigningChallenge.objects.get(digest=signed["digest"])
            spend(challenge, signed["signature"])
            with self.assertRaises(IntegrityError), atomic():
                OrderSubmission.objects.filter(pk=self.submission().pk).update(
                    status="created",
                    executed_challenge=challenge,
                    resolved_at=timezone.now(),
                    order=self.tenant.order,
                )
            original = self.submission()
            order = TransferOrder.objects.create(
                token=original.token,
                wallet=self.wallet,
                owner_account=self.tenant.account,
                wallet_address=original.wallet_address,
                order_type=original.order_type,
                quantity=original.quantity,
                min_quantity=original.min_quantity,
                price_per_share=original.price_per_share,
            )
            outcome = {
                "status": "created",
                "executed_challenge": challenge,
                "resolved_at": timezone.now(),
                "order": order,
            }
            with self.assertRaises(IntegrityError), atomic():
                OrderSubmission.objects.filter(pk=original.pk).update(
                    **outcome, initial_counter_order=self.tenant.order, initial_swap=self.tenant.swap
                )
            OrderSubmission.objects.filter(pk=original.pk).update(**outcome)
        self.assertEqual(self.recover().json()["order"]["uuid"], str(order.pk))
