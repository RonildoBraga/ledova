from decimal import Decimal
from unittest.mock import Mock, patch

from django.conf import settings
from django.core.cache import cache
from eth_account import Account
from rest_framework.test import APITransactionTestCase

from assets.services.identity import native_asset_for_chain
from shared.db import acting_for, use_operator
from shared.tests.scoped import RunsOnTheScopedConnection
from shared.tests.tenants import make_tenant
from wallets.models import (
    Holding,
    HoldingSnapshot,
    Transaction,
    Wallet,
    WalletSubmission,
)
from wallets.services import transfers


class SubmissionFixture:
    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.signer = Account.create()
        self.recipient = Account.create().address
        with use_operator():
            self.tenant = make_tenant("submission-durability")
            self.wallet = Wallet.objects.create(
                user_account=self.tenant.account,
                address=self.signer.address,
                chain="base",
                verification_status="VERIFIED",
            )
            self.native = native_asset_for_chain("base")
            self.holding = Holding.objects.create(wallet=self.wallet, asset=self.native, quantity=Decimal("10"))
        self.client.force_authenticate(self.tenant.user)
        self.client.raise_request_exception = False
        for target in (
            "wallets.tasks.confirm_pending_transaction.configure",
            "wallets.services.transaction_confirmation.TransactionMonitoringService.check_new_transaction",
            "wallets.services.transaction_confirmation.send_transaction_notification.defer",
            "wallets.services.transaction_confirmation.sync_holding",
        ):
            boundary = patch(target)
            boundary.start()
            self.addCleanup(boundary.stop)

    def signed(self, **overrides):
        fields = {
            "chainId": settings.BLOCKCHAIN_CHAIN_ID,
            "nonce": 3,
            "to": self.recipient,
            "value": 2 * 10**18,
            "gas": 21000,
            "gasPrice": 2 * 10**9,
            **overrides,
        }
        if fields.get("type") == 2:
            fields.pop("gasPrice")
        return self.signer.sign_transaction(fields)

    def provider(self, signed):
        provider = Mock(
            spec=["assert_expected_chain", "get_mined_nonce", "get_transaction_receipt", "broadcast_transaction"]
        )
        provider.assert_expected_chain.return_value = settings.BLOCKCHAIN_CHAIN_ID
        provider.get_transaction_receipt.return_value = None
        provider.get_mined_nonce.side_effect = lambda address, token_contracts=(): {
            "chain_id": provider.assert_expected_chain.return_value,
            "nonce": 0,
            "balance_wei": str(10 * 10**18),
            "block_number": 100,
            "block_hash": "0x" + "ab" * 32,
            **({"token_balances": {contract: "10000000" for contract in token_contracts}} if token_contracts else {}),
        }
        provider.broadcast_transaction.return_value = signed.hash.to_0x_hex()
        return provider

    def broadcast(self, signed, **extra):
        return self.client.post(
            f"/api/wallets/{self.wallet.pk}/broadcast-transfer/",
            {"signed_transaction": signed.raw_transaction.to_0x_hex(), **extra},
            format="json",
        )

    def transactions(self):
        with use_operator():
            return list(Transaction.objects.filter(wallet=self.wallet).values())

    def financial_state(self):
        with use_operator():
            return (
                list(Transaction.objects.filter(wallet=self.wallet).order_by("pk").values()),
                list(Holding.objects.filter(wallet=self.wallet).order_by("pk").values()),
                list(HoldingSnapshot.objects.filter(holding__wallet=self.wallet).order_by("pk").values()),
            )

    def submission(self):
        with use_operator():
            return WalletSubmission.objects.get(wallet=self.wallet)

    def submit_direct(self, signed):
        with acting_for(self.tenant.user.pk):
            return transfers.broadcast_transfer(
                self.wallet, signed.raw_transaction.to_0x_hex(), principal_id=self.tenant.user.pk
            )


class SubmissionDurabilityChecks(SubmissionFixture):
    def test_signed_intent_and_nonce_are_stored_before_the_first_send_rpc(self):
        signed = self.signed()
        provider = self.provider(signed)
        observed = []

        def send(raw):
            observed.extend(self.transactions())
            self.assertEqual(bytes.fromhex(raw.removeprefix("0x")), bytes(signed.raw_transaction))
            return signed.hash.to_0x_hex()

        provider.broadcast_transaction.side_effect = send
        with patch("wallets.services.submissions.get_blockchain_client", return_value=provider):
            response = self.broadcast(signed, to_address=self.signer.address, amount="999", transaction_fee="0")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]["tx_hash"], signed.hash.to_0x_hex())
        self.assertEqual(observed[0]["nonce"], 3)
        self.assertEqual(observed[0]["to_address"], self.recipient)
        self.assertEqual(observed[0]["amount"], Decimal("2"))
        self.assertEqual(observed[0]["transaction_fee_estimated"], Decimal("0.000042"))
        submission = self.submission()
        self.assertEqual(bytes(submission.raw_transaction), bytes(signed.raw_transaction))
        self.assertEqual(submission.tx_hash, signed.hash.to_0x_hex())
        self.assertEqual(
            (submission.chain_id, submission.sender_address),
            (settings.BLOCKCHAIN_CHAIN_ID, self.signer.address.lower()),
        )
        self.assertEqual(submission.asset_id, self.native.pk)
        self.assertIsNone(submission.deployment_id)
        self.assertEqual(submission.intent["raw_amount"], str(2 * 10**18))

    def test_lost_acknowledgement_retains_the_locally_derived_pending_identity(self):
        signed = self.signed()
        provider = self.provider(signed)
        provider.broadcast_transaction.side_effect = TimeoutError("Synthetic lost acknowledgement")
        with patch("wallets.services.submissions.get_blockchain_client", return_value=provider):
            response = self.broadcast(signed)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["txHash"], signed.hash.to_0x_hex())
        rows = self.transactions()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["tx_hash"], rows[0]["status"]), (signed.hash.to_0x_hex(), "pending"))
        with use_operator():
            self.holding.refresh_from_db()
        self.assertEqual(self.holding.quantity, Decimal("7.999958"))

    def test_a_mismatching_acknowledgement_cannot_replace_the_signed_hash(self):
        signed = self.signed()
        provider = self.provider(signed)
        provider.broadcast_transaction.return_value = "0x" + "89" * 32
        with patch("wallets.services.submissions.get_blockchain_client", return_value=provider):
            response = self.broadcast(signed)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["txHash"], signed.hash.to_0x_hex())
        self.assertEqual(self.transactions()[0]["tx_hash"], signed.hash.to_0x_hex())
        self.assertIsNone(self.submission().acknowledged_at)

    def test_direct_service_calls_derive_intent_even_without_declared_metadata(self):
        signed = self.signed()
        provider = self.provider(signed)
        with (
            acting_for(self.tenant.user.pk),
            patch("wallets.services.submissions.get_blockchain_client", return_value=provider),
        ):
            result = transfers.broadcast_transfer(
                self.wallet, signed.raw_transaction.to_0x_hex(), principal_id=self.tenant.user.pk
            )
        self.assertEqual(result["txHash"], signed.hash.to_0x_hex())
        rows = self.transactions()
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            (rows[0]["amount"], rows[0]["to_address"], rows[0]["nonce"]), (Decimal("2"), self.recipient, 3)
        )


class SubmissionDurabilityTest(SubmissionDurabilityChecks, APITransactionTestCase):
    pass


class ScopedSubmissionDurabilityTest(RunsOnTheScopedConnection, SubmissionDurabilityChecks, APITransactionTestCase):
    pass
