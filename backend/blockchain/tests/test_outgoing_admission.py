import traceback
from unittest.mock import patch

from django.contrib import admin
from django.db import IntegrityError, connection
from django.forms import modelform_factory
from django.test import TransactionTestCase

from blockchain.constants import MAX_SIGNER_ADMISSION_GENERATION
from blockchain.models import (
    OutgoingOperation,
    OutgoingStatus,
    SignedAttempt,
    SignerAdmission,
    SigningAccount,
)
from blockchain.services.outgoing import (
    OutgoingTransactionError,
    PreparedTransaction,
    broadcast_operation,
    close_signer_admission,
    prepare_operation,
    reconcile_operation,
    sign_operation,
)
from blockchain.tests.outgoing_fixtures import (
    CHAIN_ID,
    KEY,
    SENDER,
    TARGET,
    admitted_signer,
    chain_client,
    claim_operation,
    receipt,
    sign_claim,
)
from shared.db import atomic


class OutgoingAdmissionTest(TransactionTestCase):
    def setUp(self):
        self.claim = claim_operation()
        self.chain = chain_client()

    def test_missing_signer_refuses_before_preparation_rpc(self):
        with self.assertRaisesMessage(OutgoingTransactionError, "admission"):
            prepare_operation(self.claim, self.chain)
        self.assertEqual(self.chain.mock_calls, [])
        self.assertFalse(SigningAccount.objects.exists())

    def test_existing_counter_cannot_authorize_preparation(self):
        signer = SigningAccount.objects.create(chain_id=CHAIN_ID, address=SENDER.lower(), next_nonce=77)
        with self.assertRaisesMessage(OutgoingTransactionError, "admission"):
            prepare_operation(self.claim, self.chain)
        self.assertEqual(self.chain.mock_calls, [])
        signer.refresh_from_db()
        self.assertEqual(signer.next_nonce, 77)
        self.assertEqual((signer.admission_state, signer.admission_generation), (SignerAdmission.CLOSED, 0))

    def test_missing_admission_refuses_direct_signing_without_allocating_a_nonce(self):
        prepared = PreparedTransaction(self.claim, CHAIN_ID, SENDER.lower(), TARGET, 3, "0x1234", 7, 60000, 10**9, 1)
        with patch("eth_account.signers.local.LocalAccount.sign_transaction") as sign:
            with self.assertRaisesMessage(OutgoingTransactionError, "admission"):
                sign_operation(self.claim, prepared, KEY)
        sign.assert_not_called()
        self.assertFalse(SigningAccount.objects.exists())
        self.assertFalse(SignedAttempt.objects.exists())

    def test_explicit_synthetic_admission_allows_preparation_signing_and_broadcast(self):
        admitted_signer(generation=3)
        prepared = prepare_operation(self.claim, self.chain)
        self.assertEqual(prepared.admission_generation, 3)
        attempt = sign_operation(self.claim, prepared, KEY)
        self.chain.send_raw_transaction.return_value = attempt.tx_hash
        self.assertTrue(broadcast_operation(self.claim, self.chain).acknowledged)
        self.chain.send_raw_transaction.assert_called_once_with(bytes(attempt.raw_transaction))
        self.assertEqual(SigningAccount.objects.get().next_nonce, 8)

    def test_close_during_preparation_rpc_does_not_hold_a_transaction_or_allow_signing(self):
        admitted_signer()

        def nonce(sender):
            self.assertFalse(connection.in_atomic_block)
            self.assertTrue(connection.get_autocommit())
            self.assertEqual(close_signer_admission(chain_id=CHAIN_ID, sender=sender), 2)
            return 7

        self.chain.get_nonce.side_effect = nonce
        prepared = prepare_operation(self.claim, self.chain)
        self.assertEqual(prepared.admission_generation, 1)
        with patch("eth_account.signers.local.LocalAccount.sign_transaction") as sign:
            with self.assertRaisesMessage(OutgoingTransactionError, "admission is closed"):
                sign_operation(self.claim, prepared, KEY)
        sign.assert_not_called()
        self.assertEqual(SigningAccount.objects.get().next_nonce, 0)
        self.assertFalse(SignedAttempt.objects.exists())

    def test_prepared_worker_cannot_survive_a_close_and_synthetic_readmission(self):
        signer = admitted_signer()
        prepared = prepare_operation(self.claim, self.chain)
        self.assertEqual(close_signer_admission(chain_id=CHAIN_ID, sender=SENDER), 2)
        SigningAccount.objects.filter(pk=signer.pk).update(
            admission_state=SignerAdmission.ADMITTED, admission_generation=3
        )
        with patch("eth_account.signers.local.LocalAccount.sign_transaction") as sign:
            with self.assertRaisesMessage(OutgoingTransactionError, "generation has changed"):
                sign_operation(self.claim, prepared, KEY)
        sign.assert_not_called()
        self.assertFalse(SignedAttempt.objects.exists())
        self.assertEqual(SigningAccount.objects.get().next_nonce, 0)
        self.assertEqual(sign_claim(self.claim).nonce, 7)

    def test_close_preserves_every_signed_attempt_claim_outcome_and_nonce_reservation(self):
        admitted_signer()
        attempt = sign_claim(self.claim)
        self.chain.send_raw_transaction.side_effect = RuntimeError("synthetic response lost")
        self.assertFalse(broadcast_operation(self.claim, self.chain).acknowledged)
        before_operations = list(OutgoingOperation.objects.values())
        before_attempts = list(SignedAttempt.objects.values())
        self.assertEqual(close_signer_admission(chain_id=CHAIN_ID, sender=SENDER), 2)
        self.assertEqual(close_signer_admission(chain_id=CHAIN_ID, sender=SENDER), 3)
        self.assertEqual(list(OutgoingOperation.objects.values()), before_operations)
        self.assertEqual(list(SignedAttempt.objects.values()), before_attempts)
        signer = SigningAccount.objects.get()
        self.assertEqual((signer.admission_state, signer.admission_generation, signer.next_nonce), ("closed", 3, 8))
        self.chain.reset_mock()
        with self.assertRaisesMessage(OutgoingTransactionError, "admission is closed"):
            broadcast_operation(self.claim, self.chain)
        self.assertEqual(self.chain.mock_calls, [])
        self.assertEqual(bytes(SignedAttempt.objects.get().raw_transaction), bytes(attempt.raw_transaction))

    def test_a_signed_winner_does_not_bypass_closed_admission_on_a_repeated_sign_call(self):
        admitted_signer()
        prepared = prepare_operation(self.claim, self.chain)
        attempt = sign_operation(self.claim, prepared, KEY)
        close_signer_admission(chain_id=CHAIN_ID, sender=SENDER)
        with self.assertRaisesMessage(OutgoingTransactionError, "admission is closed"):
            sign_operation(self.claim, prepared, KEY)
        self.assertEqual(OutgoingOperation.objects.get().current_attempt_id, attempt.pk)
        self.assertEqual(SignedAttempt.objects.count(), 1)

    def test_closed_replay_can_resume_only_the_same_bytes_after_synthetic_readmission(self):
        signer = admitted_signer()
        attempt = sign_claim(self.claim)
        close_signer_admission(chain_id=CHAIN_ID, sender=SENDER)
        with self.assertRaisesMessage(OutgoingTransactionError, "admission is closed"):
            broadcast_operation(self.claim, self.chain)
        self.assertEqual(self.chain.mock_calls, [])
        SigningAccount.objects.filter(pk=signer.pk).update(
            admission_state=SignerAdmission.ADMITTED, admission_generation=3
        )
        self.chain.send_raw_transaction.return_value = attempt.tx_hash
        self.assertTrue(broadcast_operation(self.claim, self.chain).acknowledged)
        self.chain.send_raw_transaction.assert_called_once_with(bytes(attempt.raw_transaction))
        self.assertEqual(SigningAccount.objects.get().next_nonce, 8)

    def test_closed_admission_still_allows_receipt_reconciliation_and_retains_unknown_outcomes(self):
        admitted_signer()
        attempt = sign_claim(self.claim)
        close_signer_admission(chain_id=CHAIN_ID, sender=SENDER)
        self.assertFalse(reconcile_operation(self.claim, self.chain))
        self.assertEqual(OutgoingOperation.objects.get().status, OutgoingStatus.SIGNED)
        self.chain.get_transaction_receipt.return_value = receipt(attempt)
        self.assertTrue(reconcile_operation(self.claim, self.chain))
        self.assertFalse(reconcile_operation(self.claim, self.chain))
        self.assertEqual(OutgoingOperation.objects.get().status, OutgoingStatus.CONFIRMED)
        self.assertEqual(SigningAccount.objects.get().admission_state, SignerAdmission.CLOSED)
        self.assertEqual(SigningAccount.objects.get().next_nonce, 8)
        self.chain.send_raw_transaction.assert_not_called()

    def test_reconciled_revert_does_not_reopen_admission_for_a_new_attempt(self):
        admitted_signer()
        first = sign_claim(self.claim)
        close_signer_admission(chain_id=CHAIN_ID, sender=SENDER)
        self.chain.get_transaction_receipt.return_value = receipt(first, 0)
        self.assertTrue(reconcile_operation(self.claim, self.chain))
        next_claim = claim_operation()
        self.assertNotEqual(next_claim.claim_id, self.claim.claim_id)
        self.chain.reset_mock()
        with self.assertRaisesMessage(OutgoingTransactionError, "admission is closed"):
            prepare_operation(next_claim, self.chain)
        self.assertEqual(self.chain.mock_calls, [])
        self.assertEqual(SignedAttempt.objects.count(), 1)
        self.assertEqual(SigningAccount.objects.get().next_nonce, 8)

    def test_closing_a_missing_signer_creates_only_a_closed_generation(self):
        self.assertEqual(close_signer_admission(chain_id=CHAIN_ID, sender=SENDER), 1)
        signer = SigningAccount.objects.get()
        self.assertEqual((signer.admission_state, signer.admission_generation, signer.next_nonce), ("closed", 1, 0))
        with self.assertRaisesMessage(OutgoingTransactionError, "admission is closed"):
            prepare_operation(self.claim, self.chain)
        self.assertEqual(self.chain.mock_calls, [])

    def test_closure_refuses_app_alias_wrapping_transaction_and_disabled_autocommit(self):
        with patch("blockchain.services.outgoing.current_alias", return_value="app"):
            with self.assertRaisesMessage(OutgoingTransactionError, "operator connection"):
                close_signer_admission(chain_id=CHAIN_ID, sender=SENDER)
        with atomic(), self.assertRaisesMessage(OutgoingTransactionError, "outside every transaction"):
            close_signer_admission(chain_id=CHAIN_ID, sender=SENDER)
        connection.set_autocommit(False)
        try:
            with self.assertRaisesMessage(OutgoingTransactionError, "outside every transaction"):
                close_signer_admission(chain_id=CHAIN_ID, sender=SENDER)
        finally:
            connection.rollback()
            connection.set_autocommit(True)
        self.assertFalse(SigningAccount.objects.exists())
        self.assertEqual(close_signer_admission(chain_id=CHAIN_ID, sender=SENDER), 1)

    def test_the_last_generation_can_only_close_and_exhaustion_never_wraps(self):
        admitted_signer(generation=MAX_SIGNER_ADMISSION_GENERATION - 1)
        attempt = sign_claim(self.claim)
        self.assertEqual(close_signer_admission(chain_id=CHAIN_ID, sender=SENDER), MAX_SIGNER_ADMISSION_GENERATION)
        with self.assertRaisesMessage(OutgoingTransactionError, "generation is exhausted"):
            close_signer_admission(chain_id=CHAIN_ID, sender=SENDER)
        signer = SigningAccount.objects.get()
        self.assertEqual(signer.admission_generation, MAX_SIGNER_ADMISSION_GENERATION)
        self.assertEqual(signer.admission_state, SignerAdmission.CLOSED)
        self.assertEqual(signer.next_nonce, 8)
        self.assertEqual(OutgoingOperation.objects.get().current_attempt_id, attempt.pk)

    def test_database_refuses_unknown_admission_and_unclosable_or_initial_admitted_generations(self):
        for state, generation in (("unknown", 1), ("admitted", 0), ("admitted", MAX_SIGNER_ADMISSION_GENERATION)):
            with self.subTest(state=state, generation=generation):
                with self.assertRaises(IntegrityError), atomic():
                    SigningAccount.objects.create(
                        chain_id=CHAIN_ID,
                        address=SENDER.lower(),
                        admission_state=state,
                        admission_generation=generation,
                    )
        self.assertFalse(SigningAccount.objects.exists())
        self.assertEqual(admitted_signer().admission_generation, 1)

    def test_failed_closure_rolls_back_and_suppresses_database_error_details(self):
        admitted_signer()
        attempt = sign_claim(self.claim)
        secret = bytes(attempt.raw_transaction).hex()
        with patch.object(SigningAccount, "save", side_effect=RuntimeError(secret)):
            try:
                close_signer_admission(chain_id=CHAIN_ID, sender=SENDER)
            except OutgoingTransactionError:
                self.assertNotIn(secret, traceback.format_exc())
            else:
                self.fail("A failed closure must refuse without claiming success")
        signer = SigningAccount.objects.get()
        self.assertEqual((signer.admission_state, signer.admission_generation, signer.next_nonce), ("admitted", 1, 8))

    def test_admission_fields_have_no_admin_or_form_edit_surface(self):
        self.assertNotIn(SigningAccount, admin.site._registry)
        form = modelform_factory(SigningAccount, fields="__all__")
        for field in ("admission_state", "admission_generation"):
            self.assertFalse(SigningAccount._meta.get_field(field).editable)
            self.assertNotIn(field, form.base_fields)
