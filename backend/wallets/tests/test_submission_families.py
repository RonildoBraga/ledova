from decimal import Decimal
from unittest.mock import patch

from rest_framework.test import APITransactionTestCase
from web3 import Web3

from shared.db import use_operator
from shared.tests.scoped import RunsOnTheScopedConnection
from wallets.models import Holding, Transaction, WalletSubmission
from wallets.services.holdings import sync_holding
from wallets.tests.test_submission_durability import SubmissionFixture


class SubmissionFamilyFixture(SubmissionFixture):

    def setUp(self):
        super().setUp()
        self.state = {
            "chain_id": 1,
            "nonce": 0,
            "balance_wei": str(10 * 10**18),
            "block_number": 100,
            "block_hash": "0x" + "ab" * 32,
        }
        self.provider_client = self.provider(self.signed())
        self.state["chain_id"] = self.provider_client.assert_expected_chain.return_value
        self.provider_client.get_mined_nonce.side_effect = lambda address: dict(self.state)
        self.provider_client.broadcast_transaction.side_effect = lambda raw: Web3.keccak(
            bytes.fromhex(raw.removeprefix("0x"))
        ).to_0x_hex()
        for target in (
            "wallets.services.submissions.get_blockchain_client",
            "wallets.services.family_balances.get_blockchain_client",
        ):
            boundary = patch(target, return_value=self.provider_client)
            boundary.start()
            self.addCleanup(boundary.stop)

    def quantity(self):
        with use_operator():
            return Holding.objects.get(pk=self.holding.pk).quantity

    def family(self):
        with use_operator():
            return (
                WalletSubmission.objects.select_related(
                    "family__selected", "family__winner__transaction", "family__winner_observation"
                )
                .filter(wallet=self.wallet)
                .order_by("created_at")
                .first()
                .family
            )

    def prepare_competing_attempts(self):
        original = self.signed()
        bump = self.signed(gasPrice=4 * 10**9)
        cancel = self.signed(to=self.signer.address, value=0, gasPrice=8 * 10**9)
        for signed in (original, bump, cancel):
            self.assertEqual(self.broadcast(signed).status_code, 200)
        return original, bump, cancel

    def mined(self, signed, *, succeeded=True, balance="7.999958", gas_price=2 * 10**9):
        from unittest.mock import Mock

        self.state["nonce"] = 4
        self.state["balance_wei"] = str(int(Decimal(balance) * 10**18))
        self.provider_client.get_transaction_receipt.side_effect = lambda tx_hash: (
            {
                "transactionHash": signed.hash.to_0x_hex(),
                "blockHash": self.state["block_hash"],
                "blockNumber": self.state["block_number"],
                "status": int(succeeded),
                "gasUsed": 21000,
                "effectiveGasPrice": gas_price,
            }
            if tx_hash == signed.hash.to_0x_hex()
            else None
        )
        self.provider_client.w3 = Mock()
        self.provider_client.w3.eth.get_block.side_effect = lambda identifier: {
            "hash": self.state["block_hash"],
            "number": self.state["block_number"],
            "timestamp": 1700000000,
        }

    def confirm(self, signed):
        from wallets.tasks.confirmation import confirm_pending_transaction

        with patch("wallets.services.chain_observations.get_blockchain_client", return_value=self.provider_client):
            return confirm_pending_transaction(
                signed.hash.to_0x_hex(), str(self.wallet.pk), principal_id=self.tenant.user.pk
            )

    def assert_winner(self, signed, *, status, quantity):
        from wallets.models import WalletChainObservation

        self.assertEqual(self.confirm(signed)["status"], status)
        self.assertEqual(self.quantity(), Decimal(quantity))
        with use_operator():
            family = self.family()
            self.assertEqual(family.winner.tx_hash, signed.hash.to_0x_hex())
            self.assertEqual(family.winner.transaction.status, status)
            losers = Transaction.objects.filter(submission__family=family).exclude(pk=family.winner.transaction_id)
            self.assertTrue(
                all(tx.status == "replaced" and tx.replaced_by_tx_hash == signed.hash.to_0x_hex() for tx in losers)
            )
            self.assertFalse(
                Transaction.objects.filter(
                    submission__family=family, balance_reconciliation_token__isnull=False
                ).exists()
            )
            self.assertEqual(
                WalletChainObservation.objects.filter(watch__wallet=self.wallet, result="included").count(), 1
            )
            self.assertEqual(
                Holding.objects.get(pk=self.holding.pk).balance_projection.observation["block_hash"],
                self.state["block_hash"],
            )
        before = self.financial_state()
        self.assertEqual(self.confirm(signed)["status"], "already_processed")
        self.assertEqual(self.financial_state(), before)

    def submission_for(self, signed):
        with use_operator():
            return WalletSubmission.objects.get(wallet=self.wallet, tx_hash=signed.hash.to_0x_hex())


class SubmissionFamilyChecks(SubmissionFamilyFixture):

    def test_speed_up_is_a_second_immutable_attempt_with_one_maximum_reservation(self):
        original = self.signed()
        bump = self.signed(gasPrice=4 * 10**9)
        self.assertEqual(self.broadcast(original).status_code, 200)
        self.assertEqual(self.broadcast(bump).status_code, 200)
        self.assertEqual(self.quantity(), Decimal("7.999916"))
        with use_operator():
            self.assertEqual(WalletSubmission.objects.filter(wallet=self.wallet).count(), 2)
            self.assertEqual(Transaction.objects.filter(wallet=self.wallet).count(), 2)
            self.assertEqual(
                set(bytes(row.raw_transaction) for row in WalletSubmission.objects.filter(wallet=self.wallet)),
                {bytes(original.raw_transaction), bytes(bump.raw_transaction)},
            )

    def test_cancellation_keeps_original_principal_until_a_winner_is_known(self):
        self.assertEqual(self.broadcast(self.signed()).status_code, 200)
        cancel = self.signed(to=self.signer.address, value=0, gasPrice=4 * 10**9)
        self.assertEqual(self.broadcast(cancel).status_code, 200)
        self.assertEqual(self.quantity(), Decimal("7.999958"))

    def test_distinct_nonce_families_cannot_each_spend_the_same_chain_balance(self):
        self.assertEqual(self.broadcast(self.signed(value=6 * 10**18)).status_code, 200)
        response = self.broadcast(self.signed(nonce=4, value=6 * 10**18))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(self.transactions()), 1)
        self.assertEqual(self.quantity(), Decimal("3.999958"))

    def test_zero_extra_cancellation_can_fit_when_original_principal_is_underfunded(self):
        self.assertEqual(self.broadcast(self.signed()).status_code, 200)
        self.state["balance_wei"] = str(10**15)
        cancel = self.signed(to=self.signer.address, value=0, gasPrice=4 * 10**9)
        self.assertEqual(self.broadcast(cancel).status_code, 200)
        self.assertEqual(self.quantity(), Decimal("0"))

    def test_cancellation_without_enough_native_for_itself_is_refused(self):
        self.assertEqual(self.broadcast(self.signed()).status_code, 200)
        self.state["balance_wei"] = "0"
        self.assertEqual(
            self.broadcast(self.signed(to=self.signer.address, value=0, gasPrice=4 * 10**9)).status_code, 400
        )
        self.assertEqual(len(self.transactions()), 1)

    def test_sync_between_original_and_speed_up_preserves_family_reservation(self):
        self.assertEqual(self.broadcast(self.signed()).status_code, 200)
        with use_operator(), patch("wallets.services.holdings.fetch_chain_balance", return_value=Decimal("10")):
            sync_holding(self.wallet, self.native)
        self.assertEqual(self.quantity(), Decimal("7.999958"))
        self.assertEqual(self.broadcast(self.signed(gasPrice=4 * 10**9)).status_code, 200)
        self.assertEqual(self.quantity(), Decimal("7.999916"))

    def test_original_can_win_after_bump_and_cancel_without_loser_refunds(self):
        original, _, _ = self.prepare_competing_attempts()
        self.mined(original)
        self.assert_winner(original, status="confirmed", quantity="7.999958")

    def test_speed_up_winner_charges_one_principal_and_its_actual_fee(self):
        _, bump, _ = self.prepare_competing_attempts()
        self.mined(bump, balance="7.999916", gas_price=4 * 10**9)
        self.assert_winner(bump, status="confirmed", quantity="7.999916")

    def test_self_cancellation_winner_releases_principal_and_charges_only_actual_fee(self):
        _, _, cancel = self.prepare_competing_attempts()
        self.mined(cancel, balance="9.999832", gas_price=8 * 10**9)
        self.assert_winner(cancel, status="confirmed", quantity="9.999832")

    def test_reverted_winner_costs_its_fee_and_does_not_charge_the_principal(self):
        _, bump, _ = self.prepare_competing_attempts()
        self.mined(bump, succeeded=False, balance="9.999916", gas_price=4 * 10**9)
        self.assert_winner(bump, status="failed", quantity="9.999916")

    def test_self_transfer_has_no_net_principal_cost_once_canonically_included(self):
        signed = self.signed(to=self.signer.address)
        self.assertEqual(self.broadcast(signed).status_code, 200)
        self.mined(signed, balance="9.999958")
        self.assert_winner(signed, status="confirmed", quantity="9.999958")

    def test_failed_balance_read_keeps_winner_evidence_and_reconciliation_token_until_retry(self):
        original, _, _ = self.prepare_competing_attempts()
        self.mined(original)
        self.provider_client.get_mined_nonce.side_effect = TimeoutError("Synthetic bounded balance unavailable")
        self.assertEqual(self.confirm(original)["status"], "confirmed")
        with use_operator():
            family = self.family()
            self.assertEqual(family.winner.tx_hash, original.hash.to_0x_hex())
            self.assertIsNotNone(family.winner.transaction.balance_reconciliation_token)
            self.assertEqual(family.winner_observation.result, "included")
        self.assertEqual(self.quantity(), Decimal("7.999916"))
        self.provider_client.get_mined_nonce.side_effect = lambda address: dict(self.state)
        self.assertEqual(self.confirm(original)["status"], "confirmed")
        self.assertEqual(self.quantity(), Decimal("7.999958"))
        with use_operator():
            self.assertIsNone(self.family().winner.transaction.balance_reconciliation_token)

    def test_consumed_unknown_nonce_stops_delivery_and_preserves_unresolved_history(self):
        from wallets.services.submissions import attempt_submission

        original = self.signed()
        self.assertEqual(self.broadcast(original).status_code, 200)
        self.state.update(nonce=4, balance_wei=str(8 * 10**18))
        self.provider_client.broadcast_transaction.reset_mock()
        with use_operator():
            self.assertEqual(attempt_submission(self.submission().pk), "nonce_consumed")
            sync_holding(self.wallet, self.native)
            self.assertEqual(self.submission().transaction.status, "pending")
            self.assertIsNone(self.family().winner_id)
        self.provider_client.broadcast_transaction.assert_not_called()
        self.assertEqual(self.quantity(), Decimal("8"))

    def test_cancellation_must_fit_beside_other_nonce_commitments(self):
        self.assertEqual(self.broadcast(self.signed()).status_code, 200)
        self.assertEqual(self.broadcast(self.signed(nonce=4, value=10**18)).status_code, 200)
        self.state["balance_wei"] = str(10**18)
        self.assertEqual(
            self.broadcast(self.signed(to=self.signer.address, value=0, gasPrice=4 * 10**9)).status_code, 400
        )
        self.assertEqual(len(self.transactions()), 2)

    def test_unfunded_family_cannot_increase_its_exposure(self):
        self.assertEqual(self.broadcast(self.signed()).status_code, 200)
        self.state["balance_wei"] = str(10**15)
        self.assertEqual(self.broadcast(self.signed(gasPrice=4 * 10**9)).status_code, 400)
        self.assertEqual(len(self.transactions()), 1)

    def test_retry_of_superseded_bytes_keeps_identity_without_selecting_or_sending_them(self):
        original, bump, cancel = self.prepare_competing_attempts()
        self.provider_client.broadcast_transaction.reset_mock()
        before = self.financial_state()
        self.assertEqual(self.broadcast(original).json()["txHash"], original.hash.to_0x_hex())
        self.assertEqual(self.financial_state(), before)
        self.assertEqual(self.family().selected.tx_hash, cancel.hash.to_0x_hex())
        self.provider_client.broadcast_transaction.assert_not_called()

    def test_explicit_orphan_evidence_reopens_family_and_new_winner_retains_old_observations(self):
        from wallets.models import WalletChainObservation
        from wallets.services.chain_observations import observe_wallet_chain

        original, bump, _ = self.prepare_competing_attempts()
        self.mined(original)
        self.confirm(original)
        old_hash = self.state["block_hash"]
        self.state.update(nonce=0, balance_wei=str(10 * 10**18), block_hash="0x" + "cd" * 32)
        self.provider_client.get_transaction_receipt.side_effect = None
        self.provider_client.get_transaction_receipt.return_value = None
        with use_operator(), patch(
            "wallets.services.chain_observations.get_blockchain_client", return_value=self.provider_client
        ):
            self.assertEqual(
                observe_wallet_chain(self.submission_for(original).transaction_id, reconcile=True), "recorded"
            )
            family = self.family()
            self.assertIsNone(family.winner_id)
            self.assertEqual(family.winner_observation.result, "orphaned")
            self.assertTrue(
                WalletChainObservation.objects.filter(
                    watch__wallet=self.wallet, result="included", evidence__receipt__hash=old_hash
                ).exists()
            )
        self.assertEqual(self.quantity(), Decimal("7.999916"))
        self.mined(bump, balance="7.999916", gas_price=4 * 10**9)
        self.assertEqual(self.confirm(bump)["status"], "confirmed")
        with use_operator():
            self.assertEqual(self.family().winner.tx_hash, bump.hash.to_0x_hex())
            self.assertEqual(WalletChainObservation.objects.filter(watch__wallet=self.wallet).count(), 3)

    def test_newer_unknown_observation_during_balance_read_discards_stale_retained_winner_projection(self):
        from wallets.models import WalletBalanceProjection, WalletChainObservation
        from wallets.services.chain_observations import (
            claim_chain_observation,
            complete_chain_observation,
            observe_wallet_chain,
        )
        from wallets.services.family_confirmation import reconcile_family_observation

        signed = self.signed()
        self.assertEqual(self.broadcast(signed).status_code, 200)
        self.mined(signed)
        self.assertEqual(self.confirm(signed)["status"], "confirmed")
        tx_id = self.submission_for(signed).transaction_id
        with patch("wallets.services.chain_observations.get_blockchain_client", return_value=self.provider_client):
            self.assertEqual(observe_wallet_chain(tx_id), "recorded")
        with use_operator():
            observation = (
                WalletChainObservation.objects.filter(watch__transaction_id=tx_id).order_by("-generation").first()
            )
            projection_count = WalletBalanceProjection.objects.filter(wallet=self.wallet).count()
        before = self.financial_state()

        def newer_unknown(address):
            claim = claim_chain_observation(tx_id)
            self.assertEqual(
                complete_chain_observation(
                    claim,
                    {"result": "unknown", "finality": "unknown", "reason": "provider_unavailable", "evidence": {}},
                ),
                "recorded",
            )
            return dict(self.state)

        self.provider_client.get_mined_nonce.side_effect = newer_unknown
        self.assertEqual(
            reconcile_family_observation(observation.pk, client=self.provider_client), "observation_changed"
        )
        self.assertEqual(self.financial_state(), before)
        with use_operator():
            self.assertEqual(WalletBalanceProjection.objects.filter(wallet=self.wallet).count(), projection_count)

    def test_replacement_fee_terms_advance_for_type_one_and_type_two(self):
        for nonce, fields, bumped, invalid in (
            (3, {"type": 1, "accessList": []}, {"gasPrice": 4 * 10**9}, {"gasPrice": 10**9}),
            (
                4,
                {"type": 2, "maxFeePerGas": 2 * 10**9, "maxPriorityFeePerGas": 10**9},
                {"maxFeePerGas": 4 * 10**9, "maxPriorityFeePerGas": 2 * 10**9},
                {"maxFeePerGas": 4 * 10**9, "maxPriorityFeePerGas": 5 * 10**8},
            ),
        ):
            with self.subTest(envelope=fields["type"]):
                original = self.signed(nonce=nonce, **fields)
                self.assertEqual(self.broadcast(original).status_code, 200)
                before = self.financial_state()
                self.assertEqual(self.broadcast(self.signed(nonce=nonce, **{**fields, **invalid})).status_code, 400)
                self.assertEqual(self.financial_state(), before)
                self.assertEqual(self.broadcast(self.signed(nonce=nonce, **{**fields, **bumped})).status_code, 200)
        self.assertEqual(self.quantity(), Decimal("5.999832"))

    def test_removed_and_readded_membership_during_rpc_is_a_new_authorization_target(self):
        with use_operator():
            profile_ids = list(self.tenant.account.user_profiles.values_list("pk", flat=True))

        def replace_membership(address):
            with use_operator():
                self.tenant.account.user_profiles.clear()
                self.tenant.account.user_profiles.add(*profile_ids)
            return dict(self.state)

        self.provider_client.get_mined_nonce.side_effect = replace_membership
        self.assertEqual(self.broadcast(self.signed()).status_code, 400)
        self.assertEqual(self.transactions(), [])
        self.provider_client.broadcast_transaction.assert_not_called()

    def test_a_family_does_not_prevent_unrelated_share_holding_sync(self):
        from assets.models import Asset

        self.assertEqual(self.broadcast(self.signed()).status_code, 200)
        with use_operator():
            asset = Asset.objects.create(symbol="SHARESYNC", name="Share sync fixture", asset_type="tokenized_security")
            holding = Holding.objects.create(wallet=self.wallet, asset=asset, quantity=Decimal("1"))
            with patch("wallets.services.holdings.fetch_chain_balance", return_value=Decimal("2")):
                self.assertEqual(sync_holding(self.wallet, asset).quantity, Decimal("2"))
            holding.refresh_from_db()
            self.assertEqual(holding.quantity, Decimal("2"))
        self.assertEqual(self.quantity(), Decimal("7.999958"))


class SubmissionFamilyTest(SubmissionFamilyChecks, APITransactionTestCase):
    pass


class ScopedSubmissionFamilyTest(RunsOnTheScopedConnection, SubmissionFamilyChecks, APITransactionTestCase):
    pass
