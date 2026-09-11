from copy import deepcopy
from datetime import timedelta
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.db import IntegrityError
from django.test import TestCase, TransactionTestCase, override_settings

from assets.models import AssetChainDeployment
from operators.models import Operator, ReceivingChain
from shared.db import atomic
from shared.tests.schema import migrate_to, restore_every_migration
from tokens.models import SwapOrder, SwapOrderStatus
from tokens.services.atomic_swap_service import payment_address
from tokens.tests.swap_state_fixtures import (
    BUYER,
    CONTRACT,
    SELLER,
    make_swap,
    persisted_outcome,
    swap_service,
)

IS_POSTGRES = settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"
_migration_modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("tokens" in _migration_modules and _migration_modules["tokens"] is None)


@skipUnless(IS_POSTGRES, "Requires the actual PostgreSQL settlement trigger")
@override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT)
class SwapSettlementStorageTest(TestCase):
    def test_identity_updates_and_delete_refuse_while_both_signature_writes_remain_legal(self):
        swap = make_swap("settlement-guard", ready=True)
        before = persisted_outcome(swap)
        changed_context = deepcopy(swap.settlement_context)
        changed_context["typed_data"]["domain"]["verifyingContract"] = "0x" + "79" * 20
        for field, value in (
            ("settlement_protocol_version", 0),
            ("settlement_context", changed_context),
            ("settlement_context", None),
            ("settlement_digest", "0x" + "bb" * 32),
            ("share_amount", swap.share_amount + 1),
            ("payment_amount", swap.payment_amount + 1),
            ("nonce", swap.nonce + 1),
            ("order_hash", "aa" * 32),
            ("expires_at", swap.expires_at + timedelta(seconds=1)),
            ("created_at", swap.created_at + timedelta(seconds=1)),
            ("seller_wallet_id", swap.buyer_wallet_id),
            ("seller_address", BUYER.address),
        ):
            with self.subTest(field=field), self.assertRaises(IntegrityError), atomic():
                SwapOrder.objects.filter(pk=swap.pk).update(**{field: value})
            self.assertEqual(persisted_outcome(swap), before)
        with self.assertRaises(IntegrityError), atomic():
            SwapOrder.objects.filter(pk=swap.pk).delete()
        self.assertEqual(persisted_outcome(swap), before)
        SwapOrder.objects.filter(pk=swap.pk).update(status=SwapOrderStatus.EXECUTING, error_message="pending")
        swap.refresh_from_db()
        self.assertEqual(
            (swap.seller_signature, swap.buyer_signature), (before[0]["seller_signature"], before[0]["buyer_signature"])
        )
        self.assertEqual(swap.status, SwapOrderStatus.EXECUTING)

    def test_database_refuses_identity_change_during_real_signature_validation(self):
        from eth_account.messages import encode_typed_data

        swap = make_swap("settlement-sign-guard")
        service = swap_service()
        signature = SELLER.sign_message(encode_typed_data(full_message=service.get_typed_data(swap))).signature.hex()
        verify = service.verify_signature

        def change(*args):
            self.assertTrue(verify(*args))
            SwapOrder.objects.filter(pk=swap.pk).update(share_amount=swap.share_amount + 1)
            return True

        with patch.object(service, "verify_signature", side_effect=change), self.assertRaises(IntegrityError), atomic():
            service.submit_signature(swap, signature, SELLER.address)
        swap.refresh_from_db()
        self.assertFalse(swap.seller_signature)
        with patch("tokens.services.atomic_swap_service.publish_trading_event"):
            signed = service.submit_signature(swap, signature, SELLER.address)
        self.assertEqual(signed.seller_signature, signature)


@skipUnless(MIGRATIONS_ENABLED, "Requires actual settlement migrations")
@override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT, SWAP_ORDER_EXPIRY_HOURS=24)
class SwapSettlementMigrationTest(TransactionTestCase):
    def test_actual_legacy_payment_address_retains_the_existing_receiving_chain_selector(self):
        swap = make_swap("settlement-legacy-asset")
        self.addCleanup(restore_every_migration)
        try:
            migrate_to([("tokens", "0038_order_action_submissions")])
        finally:
            restore_every_migration()
        swap.refresh_from_db()
        self.assertEqual(swap.settlement_protocol_version, 0)
        self.assertEqual(payment_address(swap), "0x" + "5" * 40)
        address = "0x" + "e" * 40
        AssetChainDeployment.objects.create(
            asset=swap.payment_asset, chain="ethereum", contract_address=address, decimals=2
        )
        operator = Operator.get()
        operator.receiving_wallet_chain = ReceivingChain.ETHEREUM
        operator.save(update_fields=["receiving_wallet_chain"])
        self.assertEqual(payment_address(swap), address)

    def test_legacy_rows_signatures_deadlines_and_hashless_claims_remain_unrebound(self):
        swap = make_swap("settlement-migration", ready=True)
        service = swap_service()
        seller_signature, buyer_signature = swap.seller_signature, swap.buyer_signature
        old_apps = migrate_to([("tokens", "0038_order_action_submissions")])
        self.addCleanup(restore_every_migration)
        old_swaps = old_apps.get_model("tokens", "SwapOrder").objects
        before = old_swaps.filter(pk=swap.pk).values().get()
        before_orders = list(
            old_apps.get_model("tokens", "TransferOrder")
            .objects.filter(pk__in=[swap.sell_order_id, swap.buy_order_id])
            .order_by("pk")
            .values()
        )
        migrate_to([("tokens", "0039_swap_settlement_context")])
        current = SwapOrder.objects.filter(pk=swap.pk).values().get()
        self.assertEqual(current.pop("settlement_protocol_version"), 0)
        self.assertIsNone(current.pop("settlement_context"))
        self.assertEqual(current.pop("settlement_digest"), "")
        self.assertEqual(current, before)
        self.assertEqual(
            list(
                old_apps.get_model("tokens", "TransferOrder")
                .objects.filter(pk__in=[swap.sell_order_id, swap.buy_order_id])
                .order_by("pk")
                .values()
            ),
            before_orders,
        )
        swap.refresh_from_db()
        self.assertAlmostEqual((swap.expires_at - swap.created_at).total_seconds(), 86400, delta=2)
        self.assertTrue(service.verify_signature(swap, seller_signature, SELLER.address))
        self.assertTrue(service.verify_signature(swap, buyer_signature, BUYER.address))
        SwapOrder.objects.filter(pk=swap.pk).update(status=SwapOrderStatus.EXECUTING, tx_hash="")
        swap.refresh_from_db()
        untouched = persisted_outcome(swap)
        with patch("django.utils.timezone.now", return_value=swap.expires_at + timedelta(days=1)):
            self.assertIsNone(service.resolve_executing_swap(swap))
        self.assertEqual(persisted_outcome(swap), untouched)
        service.chain_client.receipt_even_if_reverted.assert_not_called()
        if IS_POSTGRES:
            with self.assertRaises(IntegrityError), atomic():
                SwapOrder.objects.filter(pk=swap.pk).update(settlement_protocol_version=1)

    def test_an_old_writer_cannot_create_an_unsnapshotted_swap_after_cutover(self):
        swap = make_swap("settlement-old-writer")
        old_apps = migrate_to([("tokens", "0038_order_action_submissions")])
        self.addCleanup(restore_every_migration)
        old_swaps = old_apps.get_model("tokens", "SwapOrder").objects
        old_values = old_swaps.filter(pk=swap.pk).values().get()
        migrate_to([("tokens", "0039_swap_settlement_context")])
        old_values.update(uuid=uuid4(), nonce=swap.nonce + 1, order_hash="cc" * 32)
        with self.assertRaises(IntegrityError), atomic():
            old_swaps.create(**old_values)
        if IS_POSTGRES:
            with self.assertRaises(IntegrityError), atomic():
                SwapOrder.objects.create(**old_values, settlement_protocol_version=0)
        fresh = make_swap("settlement-new-writer")
        self.assertEqual(fresh.settlement_protocol_version, 1)
        self.assertEqual(fresh.settlement_context["digest"], fresh.settlement_digest)
