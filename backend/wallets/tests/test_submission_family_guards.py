from decimal import Decimal
from unittest import skipUnless
from unittest.mock import patch

from django.db import DatabaseError, connections, transaction
from rest_framework.test import APITransactionTestCase

from shared.db import APP_ALIAS, atomic, configured, current_alias, use_operator
from wallets.models import Transaction, WalletChainObservation, WalletSubmission
from wallets.services.chain_observations import observe_wallet_chain
from wallets.tests.test_submission_token_families import TokenFamilyFixture

POSTGRES = connections[configured(APP_ALIAS)].vendor == "postgresql"


@skipUnless(POSTGRES, "Deferred storage guards require PostgreSQL")
class SubmissionFamilyGuardTest(TokenFamilyFixture, APITransactionTestCase):
    def assert_storage_refuses(self, operation):
        with use_operator(), atomic():
            try:
                with self.assertRaises(DatabaseError):
                    operation()
                    with connections[current_alias()].cursor() as cursor:
                        cursor.execute(
                            "SET CONSTRAINTS wallets_submission_family_complete, wallets_submission_member_complete IMMEDIATE"
                        )
            finally:
                transaction.set_rollback(True, using=current_alias())

    def test_storage_refuses_token_amount_changes_inside_a_speed_up_family(self):
        signed = self.token_signed()
        self.assertEqual(self.broadcast(signed).status_code, 200)
        original = self.submission_for(signed)
        altered = self.token_signed(gasPrice=4 * 10**9)

        def insert_changed_amount():
            family = original.family
            intent = {
                **original.intent,
                "amount": "3",
                "raw_amount": "3000000",
                "maximum_fee": "0.00036",
                "gas_price": "4000000000",
            }
            tx = Transaction.objects.create(
                wallet=self.wallet,
                asset=self.token,
                tx_hash=altered.hash.to_0x_hex(),
                chain="base",
                from_address=self.wallet.address,
                to_address=self.recipient,
                amount=Decimal("3"),
                nonce=3,
                transaction_fee_estimated=Decimal("0.00036"),
                status="pending",
            )
            attempt = WalletSubmission.objects.create(
                family=family,
                parent=original,
                kind="speed_up",
                wallet=self.wallet,
                user_account_id=self.wallet.user_account_id,
                transaction=tx,
                asset=self.token,
                deployment=self.deployment,
                chain="base",
                chain_id=original.chain_id,
                sender_address=original.sender_address,
                nonce=3,
                tx_hash=altered.hash.to_0x_hex(),
                raw_transaction=bytes(altered.raw_transaction),
                intent=intent,
            )
            family.selected = attempt
            family.native_exposure = Decimal("0.00036")
            family.generation += 1
            family.save(update_fields=["selected", "native_exposure", "generation", "updated_at"])

        self.assert_storage_refuses(insert_changed_amount)
        with use_operator():
            self.assertEqual(WalletSubmission.objects.filter(wallet=self.wallet).count(), 1)

    def included_then_orphaned(self):
        signed = self.signed()
        self.assertEqual(self.broadcast(signed).status_code, 200)
        self.mined(signed)
        self.assertEqual(self.confirm(signed)["status"], "confirmed")
        inclusion = self.family().winner_observation
        self.state.update(nonce=0, balance_wei=str(10 * 10**18), block_hash="0x" + "cd" * 32)
        self.provider_client.get_transaction_receipt.side_effect = None
        self.provider_client.get_transaction_receipt.return_value = None
        with use_operator(), patch(
            "wallets.services.chain_observations.get_blockchain_client", return_value=self.provider_client
        ):
            self.assertEqual(
                observe_wallet_chain(self.submission_for(signed).transaction_id, reconcile=True), "recorded"
            )
        self.assertIsNone(self.family().winner_id)
        return signed, inclusion, self.family().winner_observation

    def change_winner(self, winner, observation):
        with connections[current_alias()].cursor() as cursor:
            cursor.execute(
                "UPDATE wallets_walletsubmissionfamily SET winner_id = %s, winner_observation_id = %s, generation = generation + 1 WHERE uuid = %s",
                [winner, observation.pk, self.family().pk],
            )

    def test_storage_refuses_old_inclusion_after_a_current_orphan_observation(self):
        signed, inclusion, orphan = self.included_then_orphaned()
        self.assertEqual(orphan.result, "orphaned")
        self.assert_storage_refuses(lambda: self.change_winner(self.submission_for(signed).pk, inclusion))
        self.assertIsNone(self.family().winner_id)

    def test_storage_refuses_replaying_old_orphan_after_reinclusion(self):
        signed, inclusion, orphan = self.included_then_orphaned()
        self.mined(signed)
        self.assertEqual(self.confirm(signed)["status"], "confirmed")
        current = self.family().winner_observation
        self.assertNotEqual(current.pk, inclusion.pk)
        self.assert_storage_refuses(lambda: self.change_winner(None, orphan))
        self.assertEqual(self.family().winner_observation_id, current.pk)

    def test_retained_winner_survives_a_newer_unknown_observation(self):
        signed, _, _ = self.included_then_orphaned()
        self.mined(signed)
        self.assertEqual(self.confirm(signed)["status"], "confirmed")
        winner = self.family().winner_id
        observation = self.family().winner_observation_id
        self.provider_client.get_transaction_receipt.side_effect = None
        self.provider_client.get_transaction_receipt.return_value = None
        with use_operator(), patch(
            "wallets.services.chain_observations.get_blockchain_client", return_value=self.provider_client
        ):
            self.assertEqual(observe_wallet_chain(self.submission_for(signed).transaction_id), "recorded")
            self.assertEqual(
                WalletChainObservation.objects.filter(watch__wallet=self.wallet).order_by("-created_at").first().result,
                "unknown",
            )
            with atomic():
                family = self.family()
                family.generation += 1
                family.save(update_fields=["generation", "updated_at"])
                with connections[current_alias()].cursor() as cursor:
                    cursor.execute("SET CONSTRAINTS wallets_submission_family_complete IMMEDIATE")
        self.assertEqual((self.family().winner_id, self.family().winner_observation_id), (winner, observation))
