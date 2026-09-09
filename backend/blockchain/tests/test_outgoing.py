import traceback
from dataclasses import replace
from unittest.mock import patch

from django.contrib import admin
from django.db import IntegrityError, connection
from django.forms import modelform_factory
from django.test import TransactionTestCase
from eth_account import Account
from eth_account._utils.legacy_transactions import Transaction
from web3 import Web3

from blockchain.models import (
    OutgoingOperation,
    OutgoingStatus,
    SignedAttempt,
    SigningAccount,
)
from blockchain.services.outgoing import (
    OutgoingTransactionError,
    broadcast_operation,
    fail_preparing,
    prepare_operation,
    reconcile_operation,
    record_receipt,
    sign_operation,
)
from blockchain.tests.outgoing_fixtures import (
    KEY,
    SENDER,
    chain_client,
    claim_operation,
    receipt,
    sign_claim,
)
from shared.db import atomic


class OutgoingOperationTest(TransactionTestCase):
    def setUp(self):
        self.claim = claim_operation()
        self.chain = chain_client()

    def operation(self):
        return OutgoingOperation.objects.get(pk=self.claim.operation_id)

    def test_repeated_key_resolves_the_same_intent_and_changed_terms_refuse(self):
        self.assertEqual(claim_operation(sender=SENDER.lower()), self.claim)
        with self.assertRaisesMessage(OutgoingTransactionError, "different intent"):
            claim_operation(value=4)
        self.assertEqual(OutgoingOperation.objects.count(), 1)

    def test_preparation_performs_all_rpc_before_signing_locks(self):
        def outside_transaction(answer):
            def read(*args):
                self.assertTrue(connection.get_autocommit())
                self.assertFalse(connection.in_atomic_block)
                return answer

            return read

        self.chain.assert_expected_chain.side_effect = outside_transaction(31337)
        self.chain.get_nonce.side_effect = outside_transaction(7)
        self.chain.estimate_gas.side_effect = outside_transaction(60000)
        prepared = prepare_operation(self.claim, self.chain)
        self.chain.reset_mock()
        with patch(
            "integrations.base_chain.client.BaseChainClient.sign_transaction", side_effect=AssertionError("RPC signing")
        ):
            attempt = sign_operation(self.claim, prepared, KEY)
        self.assertEqual(self.chain.mock_calls, [])
        self.assertEqual(Account.recover_transaction(bytes(attempt.raw_transaction)), SENDER)

    def test_same_pending_nonce_allocates_from_the_durable_account_counter(self):
        first = sign_claim(self.claim)
        second = sign_claim(claim_operation("synthetic:2", value=4))
        third_client = chain_client()
        third_client.get_nonce.return_value = 20
        third = sign_claim(claim_operation("synthetic:3"), third_client)
        self.assertEqual([first.nonce, second.nonce, third.nonce], [7, 8, 20])
        self.assertEqual(SigningAccount.objects.get().next_nonce, 21)
        for attempt in (first, second, third):
            self.assertEqual(Transaction.from_bytes(bytes(attempt.raw_transaction)).nonce, attempt.nonce)

    def test_a_duplicate_preparer_returns_the_winners_bytes_without_signing_again(self):
        first = prepare_operation(self.claim, self.chain)
        second = replace(first, gas_price=first.gas_price * 2, observed_nonce=99)
        winner = sign_operation(self.claim, first, KEY)
        with patch(
            "eth_account.signers.local.LocalAccount.sign_transaction", side_effect=AssertionError("second signature")
        ):
            reused = sign_operation(self.claim, second, KEY)
        self.assertEqual(reused.pk, winner.pk)
        self.assertEqual(bytes(reused.raw_transaction), bytes(winner.raw_transaction))
        self.assertEqual(SigningAccount.objects.get().next_nonce, 8)

    def test_independent_signers_and_chains_have_separate_nonce_counters(self):
        first = sign_claim(self.claim)
        other_key = "0x" + "22" * 32
        second = sign_claim(claim_operation("second-signer", sender=Account.from_key(other_key).address), key=other_key)
        other_chain = chain_client()
        other_chain.assert_expected_chain.return_value = 11155111
        third = sign_claim(claim_operation("second-chain", chain_id=11155111), other_chain)
        self.assertEqual([first.nonce, second.nonce, third.nonce], [7, 7, 7])
        self.assertEqual(SigningAccount.objects.count(), 3)

    def test_contract_creation_preserves_the_missing_target_when_replayed(self):
        claim = claim_operation("synthetic:deployment", to=None)
        attempt = sign_claim(claim)
        self.assertEqual(Transaction.from_bytes(bytes(attempt.raw_transaction)).to, b"")
        self.chain.send_raw_transaction.return_value = attempt.tx_hash
        self.assertTrue(broadcast_operation(claim, self.chain).acknowledged)
        self.chain.send_raw_transaction.assert_called_once_with(bytes(attempt.raw_transaction))

    def test_stale_preparing_worker_cannot_sign_or_fail_the_replacement(self):
        prepared = prepare_operation(self.claim, self.chain)
        self.assertTrue(fail_preparing(self.claim))
        current = claim_operation()
        winner = sign_claim(current)
        with self.assertRaisesMessage(OutgoingTransactionError, "no longer current"):
            sign_operation(self.claim, prepared, KEY)
        self.assertFalse(fail_preparing(self.claim))
        self.assertEqual(self.operation().current_attempt_id, winner.pk)
        self.assertEqual(SignedAttempt.objects.count(), 1)

    def test_prepared_payload_and_signer_must_match_the_claimed_intent(self):
        prepared = prepare_operation(self.claim, self.chain)
        for changed in (replace(prepared, value=4), replace(prepared, data="0x5678"), replace(prepared, chain_id=1)):
            with self.subTest(changed=changed):
                with self.assertRaises(OutgoingTransactionError):
                    sign_operation(self.claim, changed, KEY)
        with self.assertRaisesMessage(OutgoingTransactionError, "does not belong"):
            sign_operation(self.claim, prepared, "0x" + "22" * 32)
        self.assertFalse(SigningAccount.objects.exists())

    def test_failed_journal_commit_allocates_no_nonce_and_returns_no_payload(self):
        prepared = prepare_operation(self.claim, self.chain)
        with patch.object(OutgoingOperation, "save", side_effect=RuntimeError("operation write failed")):
            with self.assertRaisesMessage(OutgoingTransactionError, "could not be committed"):
                sign_operation(self.claim, prepared, KEY)
        self.assertEqual(self.operation().status, OutgoingStatus.PREPARING)
        self.assertFalse(SignedAttempt.objects.exists())
        self.assertFalse(SigningAccount.objects.exists())
        self.chain.send_raw_transaction.assert_not_called()

    def test_wrapping_transaction_and_manual_autocommit_disable_refuse_before_rpc(self):
        with atomic():
            with self.assertRaisesMessage(OutgoingTransactionError, "outside every transaction"):
                prepare_operation(self.claim, self.chain)
            with self.assertRaises(OutgoingTransactionError):
                claim_operation("wrapped")
        connection.set_autocommit(False)
        try:
            with self.assertRaises(OutgoingTransactionError):
                prepare_operation(self.claim, self.chain)
        finally:
            connection.rollback()
            connection.set_autocommit(True)
        self.assertEqual(self.chain.mock_calls, [])

    def test_signing_and_replay_also_refuse_a_wrapping_transaction(self):
        prepared = prepare_operation(self.claim, self.chain)
        with atomic(), self.assertRaises(OutgoingTransactionError):
            sign_operation(self.claim, prepared, KEY)
        sign_operation(self.claim, prepared, KEY)
        with atomic(), self.assertRaises(OutgoingTransactionError):
            broadcast_operation(self.claim, self.chain)
        self.chain.send_raw_transaction.assert_not_called()

    def test_app_alias_is_refused_before_any_storage_or_rpc_access(self):
        with patch("blockchain.services.outgoing.current_alias", return_value="app"):
            with self.assertRaisesMessage(OutgoingTransactionError, "operator connection"):
                prepare_operation(self.claim, self.chain)
        self.assertEqual(self.chain.mock_calls, [])

    def test_lost_response_already_known_and_nonce_errors_replay_only_saved_bytes(self):
        attempt = sign_claim(self.claim)
        for message in ("response lost", "already known", "nonce too low"):
            self.chain.send_raw_transaction.side_effect = RuntimeError(message)
            result = broadcast_operation(self.claim, self.chain)
            self.assertEqual(result.tx_hash, attempt.tx_hash)
            self.assertFalse(result.acknowledged)
            self.assertFalse(reconcile_operation(self.claim, self.chain))
            self.assertFalse(fail_preparing(self.claim))
            self.assertEqual(claim_operation(), self.claim)
        self.assertEqual(
            [call.args[0] for call in self.chain.send_raw_transaction.call_args_list],
            [bytes(attempt.raw_transaction)] * 3,
        )
        self.assertEqual(self.operation().status, OutgoingStatus.SIGNED)
        self.assertEqual(SignedAttempt.objects.count(), 1)
        self.assertEqual(SigningAccount.objects.get().next_nonce, 8)

    def test_replay_refuses_corrupt_bytes_and_valid_signatures_for_different_intents_or_nonces(self):
        first = sign_claim(self.claim)
        transaction = Transaction.from_bytes(bytes(first.raw_transaction)).as_dict()
        transaction = {key: value for key, value in transaction.items() if key not in ("v", "r", "s")}
        transaction["chainId"] = 31337
        for index, changed in enumerate(
            ({"chainId": 1}, {"to": b"\xcc" * 20}, {"data": b"changed"}, {"value": 4}, {"nonce": 100}, {}), 8
        ):
            with self.subTest(changed=changed):
                claim = claim_operation(f"corrupt:{index}")
                raw = bytes(Account.sign_transaction(transaction | {"nonce": index} | changed, KEY).raw_transaction)
                attempt = SignedAttempt.objects.create(
                    operation_id=claim.operation_id,
                    claim_id=claim.claim_id,
                    signer=first.signer,
                    nonce=index,
                    tx_hash=Web3.to_hex(Web3.keccak(raw)),
                    raw_transaction=raw if changed else b"corrupt",
                )
                operation = OutgoingOperation.objects.get(pk=claim.operation_id)
                operation.current_attempt = attempt
                operation.status = OutgoingStatus.SIGNED
                operation.save(update_fields=["current_attempt", "status"])
                with self.assertRaises(OutgoingTransactionError):
                    broadcast_operation(claim, self.chain)
                self.chain.send_raw_transaction.assert_not_called()

    def test_broadcast_runs_outside_transaction_and_persists_acknowledgment(self):
        attempt = sign_claim(self.claim)

        def send(raw):
            self.assertTrue(connection.get_autocommit())
            self.assertFalse(connection.in_atomic_block)
            self.assertEqual(bytes(SignedAttempt.objects.get().raw_transaction), raw)
            return attempt.tx_hash

        self.chain.send_raw_transaction.side_effect = send
        self.assertTrue(broadcast_operation(self.claim, self.chain).acknowledged)
        self.assertIsNotNone(self.operation().acknowledged_at)

    def test_wrong_endpoint_or_returned_hash_leaves_the_recorded_identity_unresolved(self):
        attempt = sign_claim(self.claim)
        self.chain.assert_expected_chain.return_value = 1
        self.assertFalse(broadcast_operation(self.claim, self.chain).acknowledged)
        self.chain.send_raw_transaction.assert_not_called()
        self.chain.assert_expected_chain.return_value = 31337
        self.chain.send_raw_transaction.return_value = "0x" + "cc" * 32
        self.assertFalse(broadcast_operation(self.claim, self.chain).acknowledged)
        self.assertEqual(self.operation().current_attempt.tx_hash, attempt.tx_hash)
        self.assertEqual(self.operation().status, OutgoingStatus.SIGNED)

    def test_confirmation_is_idempotent_and_late_failure_cannot_undo_it(self):
        attempt = sign_claim(self.claim)
        self.assertTrue(record_receipt(self.claim, attempt.tx_hash, receipt(attempt)))
        self.assertFalse(record_receipt(self.claim, attempt.tx_hash, receipt(attempt, 0)))
        self.assertFalse(fail_preparing(self.claim))
        self.assertTrue(broadcast_operation(self.claim, self.chain).acknowledged)
        self.chain.send_raw_transaction.assert_not_called()
        self.assertEqual(self.operation().status, OutgoingStatus.CONFIRMED)

    def test_reverted_attempt_is_retained_and_its_late_receipt_cannot_complete_the_new_claim(self):
        first = sign_claim(self.claim)
        record_receipt(self.claim, first.tx_hash, receipt(first, 0))
        current = claim_operation()
        self.assertNotEqual(current.claim_id, self.claim.claim_id)
        self.assertFalse(record_receipt(self.claim, first.tx_hash, receipt(first)))
        second = sign_claim(current)
        self.assertEqual([first.nonce, second.nonce], [7, 8])
        self.assertEqual(SignedAttempt.objects.filter(operation_id=current.operation_id).count(), 2)
        self.assertEqual(bytes(SignedAttempt.objects.get(pk=first.pk).raw_transaction), bytes(first.raw_transaction))

    def test_late_losing_replay_error_cannot_fail_the_current_completed_claim(self):
        first = sign_claim(self.claim)

        def replaced_during_send(raw):
            record_receipt(self.claim, first.tx_hash, receipt(first, 0))
            current = claim_operation()
            second = sign_claim(current)
            record_receipt(current, second.tx_hash, receipt(second))
            raise RuntimeError("late old replay error")

        self.chain.send_raw_transaction.side_effect = replaced_during_send
        self.assertFalse(broadcast_operation(self.claim, self.chain).acknowledged)
        self.assertEqual(self.operation().status, OutgoingStatus.CONFIRMED)
        self.assertEqual(self.operation().last_error, "")

    def test_a_receipt_for_another_hash_cannot_complete_the_attempt(self):
        attempt = sign_claim(self.claim)
        bad = receipt(attempt) | {"transactionHash": "0x" + "cc" * 32}
        with self.assertRaisesMessage(OutgoingTransactionError, "different transaction"):
            record_receipt(self.claim, attempt.tx_hash, bad)
        self.assertEqual(self.operation().status, OutgoingStatus.SIGNED)

    def test_provider_error_details_do_not_escape_into_result_storage_or_traceback(self):
        attempt = sign_claim(self.claim)
        secret = bytes(attempt.raw_transaction).hex()
        self.chain.send_raw_transaction.side_effect = RuntimeError(secret)
        result = broadcast_operation(self.claim, self.chain)
        self.assertNotIn(secret, repr(result))
        self.assertEqual(self.operation().last_error, "RuntimeError")
        other = claim_operation("unprepared")
        self.chain.estimate_gas.side_effect = RuntimeError(secret)
        try:
            prepare_operation(other, self.chain)
        except OutgoingTransactionError:
            self.assertNotIn(secret, traceback.format_exc())
        else:
            self.fail("preparation should refuse the provider error")

    def test_database_error_details_do_not_expose_the_signed_payload(self):
        prepared = prepare_operation(self.claim, self.chain)
        observed = []

        def fail_write(row, *args, **kwargs):
            observed.append(bytes(row.current_attempt.raw_transaction).hex())
            raise RuntimeError(observed[-1])

        with patch.object(OutgoingOperation, "save", fail_write):
            try:
                sign_operation(self.claim, prepared, KEY)
            except OutgoingTransactionError:
                self.assertEqual(len(observed), 1)
                self.assertNotIn(observed[0], traceback.format_exc())
            else:
                self.fail("a failed journal write cannot return a signed payload")
        self.assertFalse(SignedAttempt.objects.exists())
        self.assertFalse(SigningAccount.objects.exists())

    def test_signed_history_cannot_be_changed_via_model_or_queryset(self):
        attempt = sign_claim(self.claim)
        with self.assertRaises(ValueError):
            attempt.save()
        with self.assertRaises(ValueError):
            attempt.delete()
        with self.assertRaises(ValueError):
            SignedAttempt.objects.filter(pk=attempt.pk).update(raw_transaction=b"corrupt")
        with self.assertRaises(ValueError):
            SignedAttempt.objects.filter(pk=attempt.pk).delete()
        self.assertEqual(
            bytes(SignedAttempt.objects.get(pk=attempt.pk).raw_transaction), bytes(attempt.raw_transaction)
        )

    def test_raw_bytes_have_no_admin_or_form_surface(self):
        for model in (OutgoingOperation, SignedAttempt, SigningAccount):
            self.assertNotIn(model, admin.site._registry)
        form = modelform_factory(SignedAttempt, fields="__all__")
        self.assertNotIn("raw_transaction", form.base_fields)
        self.assertFalse(SignedAttempt._meta.get_field("raw_transaction").editable)

    def test_database_refuses_unreserved_status_and_duplicate_nonce(self):
        with self.assertRaises(IntegrityError), atomic():
            OutgoingOperation.objects.filter(pk=self.claim.operation_id).update(status=OutgoingStatus.SIGNED)
        first = sign_claim(self.claim)
        other = claim_operation("same-nonce")
        with self.assertRaises(IntegrityError), atomic():
            SignedAttempt.objects.create(
                operation_id=other.operation_id,
                claim_id=other.claim_id,
                signer=first.signer,
                nonce=first.nonce,
                tx_hash="0x" + "cc" * 32,
                raw_transaction=bytes(first.raw_transaction),
            )
