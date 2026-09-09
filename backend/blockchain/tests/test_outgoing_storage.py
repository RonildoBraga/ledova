from contextlib import contextmanager
from unittest import skipUnless

from django.conf import settings
from django.db import DatabaseError, connection
from django.test import TransactionTestCase

from blockchain.models import OutgoingOperation, SignedAttempt, SigningAccount
from blockchain.tests.outgoing_fixtures import claim_operation, sign_claim
from shared.db import atomic


@skipUnless(
    connection.vendor == "postgresql", "PostgreSQL enforces the operator policies and immutable journal triggers"
)
class OutgoingStoragePolicyTest(TransactionTestCase):
    def setUp(self):
        self.claim = claim_operation()
        self.attempt = sign_claim(self.claim)

    @contextmanager
    def role(self, name):
        with connection.cursor() as cursor:
            cursor.execute(f"SET ROLE {connection.ops.quote_name(settings.RLS_ROLES[name])}")
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")

    def test_app_role_cannot_read_operation_nonce_or_payload_even_with_a_principal(self):
        with self.role("app"), connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.user_id', '123', false)")
            for model in (OutgoingOperation, SigningAccount, SignedAttempt):
                self.assertEqual(model.objects.count(), 0)
            cursor.execute("SELECT set_config('app.user_id', '', false)")
        self.assertEqual(SignedAttempt.objects.count(), 1)

    def test_app_role_cannot_insert_update_or_delete_outgoing_rows(self):
        with self.role("app"):
            with self.assertRaises(DatabaseError), atomic():
                OutgoingOperation.objects.create(operation_key="forbidden", intent={}, claim_id=self.claim.claim_id)
            with connection.cursor() as cursor:
                for table, field, value in (
                    ("blockchain_outgoingoperation", "last_error", "wrong"),
                    ("blockchain_signingaccount", "next_nonce", 100),
                    ("blockchain_signedattempt", "nonce", 100),
                ):
                    cursor.execute(f"UPDATE {table} SET {field} = %s", [value])
                    self.assertEqual(cursor.rowcount, 0)
                    cursor.execute(f"DELETE FROM {table}")
                    self.assertEqual(cursor.rowcount, 0)

    def test_operator_role_can_reserve_and_read_the_private_journal(self):
        with self.role("operator"):
            second = sign_claim(claim_operation("operator:second"))
            self.assertEqual(second.nonce, 8)
            self.assertEqual(
                bytes(SignedAttempt.objects.get(pk=second.pk).raw_transaction), bytes(second.raw_transaction)
            )

    def test_even_operator_sql_cannot_mutate_or_delete_signed_history(self):
        with self.role("operator"):
            for statement in (
                "UPDATE blockchain_signedattempt SET nonce = 99",
                "DELETE FROM blockchain_signedattempt",
                "UPDATE blockchain_outgoingoperation SET operation_key = 'changed'",
                "UPDATE blockchain_outgoingoperation SET intent = '{}'::jsonb",
                "UPDATE blockchain_signingaccount SET next_nonce = 0",
                "DELETE FROM blockchain_signingaccount",
            ):
                with self.subTest(statement=statement):
                    with self.assertRaises(DatabaseError), atomic(), connection.cursor() as cursor:
                        cursor.execute(statement)
        self.assertEqual(SigningAccount.objects.get().next_nonce, 8)
        self.assertEqual(SignedAttempt.objects.get().nonce, 7)

    def test_signed_or_completed_operation_cannot_be_reset_to_a_new_claim(self):
        with self.assertRaises(DatabaseError), atomic(), connection.cursor() as cursor:
            cursor.execute(
                "UPDATE blockchain_outgoingoperation SET current_attempt_id = NULL, status = 'preparing', "
                "claim_id = '00000000-0000-0000-0000-000000000001'"
            )
        self.assertEqual(OutgoingOperation.objects.get().current_attempt_id, self.attempt.pk)
