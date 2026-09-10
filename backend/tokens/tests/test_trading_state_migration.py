from unittest import skipUnless

from django.conf import settings
from django.db import IntegrityError
from django.test import TransactionTestCase
from django.utils import timezone

from shared.db import atomic
from shared.tests.schema import migrate_to, restore_every_migration
from shared.tests.tenants import make_tenant
from tokens.tests.signing_challenge_fixtures import historical_cancel_values

BEFORE = [("tokens", "0034_shareissuance_mint_journal")]
AFTER = [("tokens", "0035_trading_state_invariants")]
_migration_modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("tokens" in _migration_modules and _migration_modules["tokens"] is None)


@skipUnless(MIGRATIONS_ENABLED, "Requires actual token migrations")
class TradingStateMigrationRefusesInvalidHistoryTest(TransactionTestCase):

    def setUp(self):
        tenant = make_tenant("old-trading")
        self.order_id = tenant.swap.sell_order_id
        self.swap_id = tenant.swap.pk
        challenge_values = historical_cancel_values(tenant.swap.sell_order)
        self.old_apps = migrate_to(BEFORE)
        self.challenge = self.old_apps.get_model("tokens", "SigningChallenge").objects.create(**challenge_values)
        self.addCleanup(self.restore)

    def restore(self):
        self.old_apps.get_model("tokens", "TransferOrder").objects.filter(pk=self.order_id).update(
            quantity=10, filled_quantity=0, min_quantity=0
        )
        self.old_apps.get_model("tokens", "SwapOrder").objects.filter(pk=self.swap_id).update(payment_amount=10)
        self.old_apps.get_model("tokens", "SigningChallenge").objects.filter(pk=self.challenge.pk).update(
            consumed_at=None, consumed_signature=""
        )
        restore_every_migration()

    def test_preflight_reports_each_rule_without_repairing_any_row(self):
        orders = self.old_apps.get_model("tokens", "TransferOrder").objects
        swaps = self.old_apps.get_model("tokens", "SwapOrder").objects
        challenges = self.old_apps.get_model("tokens", "SigningChallenge").objects
        orders.filter(pk=self.order_id).update(quantity=1, filled_quantity=3)
        swaps.filter(pk=self.swap_id).update(payment_amount=0)
        consumed = timezone.now()
        challenges.filter(pk=self.challenge.pk).update(consumed_at=consumed, consumed_signature="")

        with self.assertRaises(RuntimeError) as refused:
            migrate_to(AFTER)

        for rule, pk in (
            ("transfer_order_filled_bounds", self.order_id),
            ("swap_order_positive_payment", self.swap_id),
            ("signing_challenge_complete_spend", self.challenge.pk),
        ):
            self.assertIn(rule, str(refused.exception))
            self.assertIn(str(pk), str(refused.exception))
        self.assertEqual(orders.get(pk=self.order_id).filled_quantity, 3)
        self.assertEqual(swaps.get(pk=self.swap_id).payment_amount, 0)
        self.assertEqual(challenges.get(pk=self.challenge.pk).consumed_at, consumed)

    def test_valid_partial_and_unresolved_legacy_rows_survive_and_new_violations_fail(self):
        orders = self.old_apps.get_model("tokens", "TransferOrder").objects
        swaps = self.old_apps.get_model("tokens", "SwapOrder").objects
        orders.filter(pk=self.order_id).update(quantity=10, filled_quantity=8, min_quantity=9, status="open")
        swaps.filter(pk=self.swap_id).update(status="executing", transaction=None, tx_hash="")

        migrated = migrate_to(AFTER)

        order = migrated.get_model("tokens", "TransferOrder").objects.get(pk=self.order_id)
        swap = migrated.get_model("tokens", "SwapOrder").objects.get(pk=self.swap_id)
        self.assertEqual((order.status, order.filled_quantity, order.min_quantity), ("open", 8, 9))
        self.assertEqual((swap.status, swap.transaction_id, swap.tx_hash), ("executing", None, ""))
        with self.assertRaises(IntegrityError), atomic():
            orders.filter(pk=self.order_id).update(filled_quantity=11)

        migrate_to(BEFORE)
        orders.filter(pk=self.order_id).update(filled_quantity=11)
        self.assertEqual(orders.get(pk=self.order_id).filled_quantity, 11)
