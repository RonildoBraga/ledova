from contextlib import contextmanager
from unittest import skipUnless
from uuid import uuid4

from django.conf import settings
from django.db import DatabaseError, connection
from django.test import TransactionTestCase

from blockchain.models import (
    OutgoingCutoverHold,
    OutgoingHistoryCapture,
    OutgoingHistoryEvidence,
)
from blockchain.services.outgoing_inventory import record_inventory
from blockchain.tests.outgoing_inventory_fixtures import snapshot
from shared.db import atomic

PRIVATE_MODELS = (OutgoingHistoryCapture, OutgoingHistoryEvidence, OutgoingCutoverHold)


@skipUnless(connection.vendor == "postgresql", "Private inventory policies and immutable triggers require PostgreSQL")
class OutgoingInventoryStorageTest(TransactionTestCase):
    def setUp(self):
        record_inventory(snapshot(), uuid4())

    @contextmanager
    def role(self, name):
        with connection.cursor() as cursor:
            cursor.execute(f"SET ROLE {connection.ops.quote_name(settings.RLS_ROLES[name])}")
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")

    def test_app_role_cannot_read_or_write_staged_raw_evidence(self):
        copies = [model.objects.values().first() for model in PRIVATE_MODELS]
        with self.role("app"), connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.user_id', '123', false)")
            for model, fields in zip(PRIVATE_MODELS, copies):
                self.assertEqual(model.objects.count(), 0)
                fields["uuid"] = uuid4()
                with self.assertRaises(DatabaseError) as refused, atomic():
                    model.objects.create(**fields)
                self.assertEqual(refused.exception.__cause__.sqlstate, "42501")
                cursor.execute(f"UPDATE {model._meta.db_table} SET updated_at = CURRENT_TIMESTAMP")
                self.assertEqual(cursor.rowcount, 0)
                cursor.execute(f"DELETE FROM {model._meta.db_table}")
                self.assertEqual(cursor.rowcount, 0)
            cursor.execute("SELECT set_config('app.user_id', '', false)")
        self.assertEqual(OutgoingHistoryCapture.objects.count(), 1)
        self.assertEqual(OutgoingHistoryEvidence.objects.count(), 1)
        self.assertGreater(OutgoingCutoverHold.objects.count(), 0)
        with self.role("operator"):
            report = record_inventory(snapshot(), uuid4())
            self.assertEqual(report["raw_valid_count"], 1)
            self.assertEqual(OutgoingHistoryCapture.objects.count(), 2)
            self.assertIsNotNone(OutgoingHistoryEvidence.objects.first().raw_transaction)

    def test_operator_cannot_mutate_committed_history_or_clear_holds(self):
        before = [list(model.objects.values()) for model in PRIVATE_MODELS]
        with self.role("operator"):
            for model in PRIVATE_MODELS:
                for statement in (
                    f"UPDATE {model._meta.db_table} SET updated_at = CURRENT_TIMESTAMP",
                    f"DELETE FROM {model._meta.db_table}",
                ):
                    with self.subTest(statement=statement):
                        with self.assertRaisesMessage(
                            DatabaseError, "cannot be changed or deleted"
                        ), atomic(), connection.cursor() as cursor:
                            cursor.execute(statement)
                with self.assertRaises(DatabaseError) as refused, atomic(), connection.cursor() as cursor:
                    cursor.execute(f"TRUNCATE {model._meta.db_table} CASCADE")
                self.assertEqual(refused.exception.__cause__.sqlstate, "42501")
        self.assertEqual([list(model.objects.values()) for model in PRIVATE_MODELS], before)

    def test_database_refuses_false_positive_evidence_and_misassigned_hold_scopes(self):
        evidence = OutgoingHistoryEvidence.objects.values().get()
        for changed in (
            {"observed_sender": None},
            {"observed_chain_id": None},
            {"observed_nonce": "-1"},
            {"observed_nonce": "07"},
            {"observed_hash": "invalid"},
            {"raw_transaction": None},
            {"raw_valid": False},
            {"expected_terms": {}},
            {"decoded_intent": {}},
            {"operation_key": ""},
            {"proved_unsigned": True},
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(DatabaseError), atomic():
                    OutgoingHistoryEvidence.objects.create(
                        **(evidence | {"uuid": uuid4(), "entry_key": str(uuid4())} | changed)
                    )
        hold = OutgoingCutoverHold.objects.filter(scope="signer").values().first()
        for changed in (
            {"scope": "deployment"},
            {"observed_chain_id": None},
            {"observed_sender": None},
            {"reason": "invented_clearance"},
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(DatabaseError), atomic():
                    OutgoingCutoverHold.objects.create(
                        **(hold | {"uuid": uuid4(), "hold_key": uuid4().hex * 2} | changed)
                    )
        self.assertEqual(OutgoingHistoryEvidence.objects.count(), 1)
