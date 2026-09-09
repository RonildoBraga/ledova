from unittest import skipUnless
from uuid import uuid4

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from eth_account import Account
from web3 import Web3

from blockchain.models import (
    OutgoingOperation,
    SignedAttempt,
    SignerAdmission,
    SigningAccount,
)
from blockchain.services.outgoing import (
    OperationClaim,
    OutgoingTransactionError,
    broadcast_operation,
)
from blockchain.tests.outgoing_fixtures import (
    CHAIN_ID,
    KEY,
    SENDER,
    TARGET,
    chain_client,
)
from shared.tests.schema import restore_every_migration

MIGRATION_MODULES = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("blockchain" in MIGRATION_MODULES and MIGRATION_MODULES["blockchain"] is None)
PREVIOUS = [("blockchain", "0005_legacy_outgoing_inventory")]
CURRENT = [("blockchain", "0006_signer_admission")]


@skipUnless(MIGRATIONS_ENABLED, "Signer default migration state requires real migrations")
class SignerAdmissionMigrationTest(TransactionTestCase):
    def test_existing_signed_history_and_new_accounts_migrate_closed_without_changing_reservations(self):
        self.addCleanup(restore_every_migration)
        executor = MigrationExecutor(connection)
        executor.migrate(PREVIOUS)
        old = executor.loader.project_state(PREVIOUS).apps
        signer = old.get_model("blockchain", "SigningAccount").objects.create(
            chain_id=CHAIN_ID, address=SENDER.lower(), next_nonce=8
        )
        operation = old.get_model("blockchain", "OutgoingOperation").objects.create(
            operation_key="synthetic:pre-admission",
            claim_id=uuid4(),
            intent={"chain_id": CHAIN_ID, "sender": SENDER.lower(), "to": TARGET, "value": "3", "data": "0x1234"},
        )
        raw = bytes(
            Account.sign_transaction(
                {
                    "chainId": CHAIN_ID,
                    "nonce": 7,
                    "to": Web3.to_checksum_address(TARGET),
                    "value": 3,
                    "data": "0x1234",
                    "gas": 60000,
                    "gasPrice": 10**9,
                },
                KEY,
            ).raw_transaction
        )
        attempt = old.get_model("blockchain", "SignedAttempt").objects.create(
            operation=operation,
            claim_id=operation.claim_id,
            signer=signer,
            nonce=7,
            tx_hash=Web3.to_hex(Web3.keccak(raw)),
            raw_transaction=raw,
        )
        operation.current_attempt = attempt
        operation.status = "signed"
        operation.save(update_fields=["current_attempt", "status"])
        before_operation = old.get_model("blockchain", "OutgoingOperation").objects.values().get(pk=operation.pk)
        before_attempt = old.get_model("blockchain", "SignedAttempt").objects.values().get(pk=attempt.pk)
        MigrationExecutor(connection).migrate(CURRENT)
        current = SigningAccount.objects.get(pk=signer.pk)
        self.assertEqual((current.admission_state, current.admission_generation, current.next_nonce), ("closed", 0, 8))
        self.assertEqual(OutgoingOperation.objects.values().get(pk=operation.pk), before_operation)
        self.assertEqual(SignedAttempt.objects.values().get(pk=attempt.pk), before_attempt)
        new = SigningAccount.objects.create(chain_id=11155111, address=SENDER.lower())
        self.assertEqual((new.admission_state, new.admission_generation), (SignerAdmission.CLOSED, 0))
        client = chain_client()
        with self.assertRaisesMessage(OutgoingTransactionError, "admission is closed"):
            broadcast_operation(OperationClaim(operation.pk, operation.claim_id), client)
        self.assertEqual(client.mock_calls, [])
