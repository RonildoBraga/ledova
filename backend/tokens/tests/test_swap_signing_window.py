import os
import runpy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import TransactionTestCase, override_settings
from eth_account.messages import encode_typed_data

from blockchain.models import BlockchainTransaction
from tokens.exceptions import SwapExpiredException
from tokens.models import SwapOrder, SwapOrderStatus, TransferOrder, TransferOrderStatus
from tokens.services.token_transfer_service import TokenTransferService
from tokens.tests.swap_state_fixtures import (
    BUYER,
    CONTRACT,
    SELLER,
    make_swap,
    persisted_outcome,
    swap_service,
)


@override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT, BLOCKCHAIN_OPERATOR_KEY="0x" + "11" * 32)
class NewlyMatchedSwapSigningWindowTest(TransactionTestCase):

    def setUp(self):
        self.now = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
        self.clock = self.enterContext(patch("django.utils.timezone.now", return_value=self.now))
        self.enterContext(self.settings(SWAP_ORDER_EXPIRY_HOURS=self.configured_hours()))
        self.enterContext(patch("tokens.services.atomic_swap_service.publish_trading_event"))
        self.template = make_swap("swap-signing-window")
        self.service = swap_service()
        TransferOrder.objects.filter(pk__in=[self.template.sell_order_id, self.template.buy_order_id]).update(
            status=TransferOrderStatus.OPEN, filled_quantity=0
        )

    def configured_hours(self, value=None):
        with patch.dict(os.environ):
            if value is None:
                os.environ.pop("SWAP_ORDER_EXPIRY_HOURS", None)
            else:
                os.environ["SWAP_ORDER_EXPIRY_HOURS"] = value
            configuration = runpy.run_path(str(Path(settings.BASE_DIR) / "ledova_backend/settings/blockchain.py"))
        return configuration["SWAP_ORDER_EXPIRY_HOURS"]

    def create_swap(self, **kwargs):
        return self.service.create_swap_order(
            self.template.sell_order, self.template.buy_order, share_amount=10, **kwargs
        )

    def signature(self, swap, signer):
        return signer.sign_message(encode_typed_data(full_message=self.service.get_typed_data(swap))).signature.hex()

    def ready_swap(self):
        swap = self.create_swap()
        self.service.submit_signature(swap, self.signature(swap, SELLER), SELLER.address)
        return self.service.submit_signature(swap, self.signature(swap, BUYER), BUYER.address)

    def test_default_matching_and_model_creation_persist_fifteen_minutes(self):
        with (
            patch(
                "tokens.services.token_transfer_service.get_base_chain_client", return_value=self.service.chain_client
            ),
            patch("tokens.services.token_transfer_service.WhitelistService"),
            patch("tokens.services.atomic_swap_service.get_base_chain_client", return_value=self.service.chain_client),
            patch("tokens.services.atomic_swap_service.WhitelistService"),
        ):
            matched = TokenTransferService().match_orders(
                self.template.buy_order, self.template.sell_order, match_quantity=10
            )
        swap = SwapOrder.objects.get(pk=matched["swap_order"].pk)
        expected = self.now + timedelta(minutes=15)
        self.template.refresh_from_db()
        self.assertEqual((swap.expires_at, self.template.expires_at), (expected, expected))
        self.assertEqual(self.service.get_typed_data(swap)["message"]["deadline"], str(int(expected.timestamp())))
        self.assertTrue(self.service.verify_signature(swap, self.signature(swap, SELLER), SELLER.address))

    def test_missing_setting_fallbacks_both_persist_fifteen_minutes(self):
        with self.settings():
            del settings.SWAP_ORDER_EXPIRY_HOURS
            model_swap = make_swap("missing-swap-window")
            service_swap = self.create_swap()
        expected = self.now + timedelta(minutes=15)
        self.assertEqual((model_swap.expires_at, service_swap.expires_at), (expected, expected))

    def test_malformed_and_nonfinite_expiry_settings_are_refused_at_import(self):
        for value in ("", "not-hours", "nan", "NaN", "inf", "-inf", "1e309", "-1e309"):
            with self.subTest(value=value), self.assertRaisesRegex(
                ImproperlyConfigured, "^SWAP_ORDER_EXPIRY_HOURS must be a finite number of hours$"
            ):
                self.configured_hours(value)

    def test_explicit_operator_and_service_hour_overrides_are_preserved(self):
        for configured, expected in (
            ("24", timedelta(hours=24)),
            ("0.5", timedelta(minutes=30)),
            ("0", timedelta(0)),
            ("-1", timedelta(hours=-1)),
        ):
            with self.subTest(configured=configured), self.settings(
                SWAP_ORDER_EXPIRY_HOURS=self.configured_hours(configured)
            ):
                self.assertEqual(self.create_swap().expires_at, self.now + expected)
        self.assertEqual(self.create_swap(expires_hours=2).expires_at, self.now + timedelta(hours=2))

    def test_signature_before_deadline_is_stored_but_late_counterparty_is_refused(self):
        swap = self.create_swap()
        seller_signature = self.signature(swap, SELLER)
        buyer_signature = self.signature(swap, BUYER)
        self.clock.return_value = self.now + timedelta(minutes=14, seconds=59)
        signed = self.service.submit_signature(swap, seller_signature, SELLER.address)
        self.assertEqual(signed.seller_signature, seller_signature)
        before = persisted_outcome(swap)
        self.clock.return_value = self.now + timedelta(minutes=15, seconds=1)
        with self.assertRaises(SwapExpiredException):
            self.service.submit_signature(swap, buyer_signature, BUYER.address)
        self.assertEqual(persisted_outcome(swap), before)

    def test_expiry_during_signature_verification_is_rechecked_before_storage(self):
        swap = self.create_swap()
        signature = self.signature(swap, SELLER)
        before = persisted_outcome(swap)
        verify = self.service.verify_signature

        def expire_after_verification(*args):
            valid = verify(*args)
            self.assertTrue(valid)
            self.clock.return_value = self.now + timedelta(minutes=15, seconds=1)
            return valid

        with patch.object(self.service, "verify_signature", side_effect=expire_after_verification):
            with self.assertRaises(SwapExpiredException):
                self.service.submit_signature(swap, signature, SELLER.address)
        self.assertEqual(persisted_outcome(swap), before)

    def test_ready_swap_after_deadline_cannot_claim_build_sign_or_send(self):
        swap = self.ready_swap()
        self.assertEqual(swap.status, SwapOrderStatus.READY)
        before = persisted_outcome(swap)
        self.clock.return_value = self.now + timedelta(minutes=15, seconds=1)
        with self.assertRaises(SwapExpiredException):
            self.service.execute_swap(swap)
        self.assertEqual(persisted_outcome(swap), before)
        self.service.chain_client.load_contract.assert_not_called()
        self.service.chain_client.build_transaction.assert_not_called()
        self.service.chain_client.sign_transaction.assert_not_called()
        self.service.chain_client.send_raw_transaction.assert_not_called()

    def test_ready_swap_before_deadline_claims_and_uses_the_recorded_deadline(self):
        swap = self.ready_swap()
        self.clock.return_value = self.now + timedelta(minutes=14, seconds=59)
        claimed, transaction = self.service._claim_execution(swap.pk)
        self.assertEqual(claimed.status, SwapOrderStatus.EXECUTING)
        self.assertEqual(claimed.transaction_id, transaction.pk)
        self.assertEqual(BlockchainTransaction.objects.filter(related_uuid=swap.pk).count(), 1)
        self.service._execute_swap_call(claimed)
        call = self.service.chain_client.load_contract.return_value.functions.executeSwap.call_args
        self.assertEqual(call.args[7], int((self.now + timedelta(minutes=15)).timestamp()))

    def test_existing_twenty_four_hour_deadline_and_issued_signatures_survive_new_default(self):
        with self.settings(SWAP_ORDER_EXPIRY_HOURS=24):
            swap = self.create_swap()
            typed_data = self.service.get_typed_data(swap)
            order_hash = swap.order_hash
            seller_signature = self.signature(swap, SELLER)
            buyer_signature = self.signature(swap, BUYER)
            self.service.submit_signature(swap, seller_signature, SELLER.address)
        self.clock.return_value = self.now + timedelta(hours=1)
        swap.refresh_from_db()
        swap.save()
        swap.refresh_from_db()
        self.assertEqual(swap.expires_at, self.now + timedelta(hours=24))
        self.assertEqual(swap.order_hash, order_hash)
        self.assertEqual(self.service.get_typed_data(swap), typed_data)
        self.assertTrue(self.service.verify_signature(swap, seller_signature, SELLER.address))
        ready = self.service.submit_signature(swap, buyer_signature, BUYER.address)
        self.assertEqual((ready.seller_signature, ready.buyer_signature), (seller_signature, buyer_signature))
        claimed, _transaction = self.service._claim_execution(ready.pk)
        self.service._execute_swap_call(claimed)
        call = self.service.chain_client.load_contract.return_value.functions.executeSwap.call_args
        self.assertEqual(call.args[7], int(typed_data["message"]["deadline"]))
        self.assertEqual(
            call.args[8:],
            (bytes.fromhex(seller_signature.removeprefix("0x")), bytes.fromhex(buyer_signature.removeprefix("0x"))),
        )
        claimed.refresh_from_db()
        self.assertEqual(claimed.expires_at, self.now + timedelta(hours=24))
        self.assertEqual(claimed.order_hash, order_hash)
