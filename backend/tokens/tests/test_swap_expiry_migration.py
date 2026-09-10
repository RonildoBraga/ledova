from unittest import skipUnless

from django.conf import settings
from django.test import TransactionTestCase

from shared.tests.schema import migrate_to, restore_every_migration
from shared.tests.tenants import make_tenant

BEFORE = [("tokens", "0035_trading_state_invariants")]
AFTER = [("tokens", "0036_swap_expiry_eligibility")]
_migration_modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("tokens" in _migration_modules and _migration_modules["tokens"] is None)


@skipUnless(MIGRATIONS_ENABLED, "Requires actual token migrations")
class SwapExpiryMigrationPreservesLegacyHistoryTest(TransactionTestCase):

    def test_existing_rows_keep_their_terms_signatures_and_reservations_without_automatic_release_eligibility(self):
        tenant = make_tenant("expiry-migration")
        old_apps = migrate_to(BEFORE)
        self.addCleanup(restore_every_migration)
        swaps = old_apps.get_model("tokens", "SwapOrder").objects
        orders = old_apps.get_model("tokens", "TransferOrder").objects
        swaps.filter(pk=tenant.swap.pk).update(
            status="ready", seller_signature="legacy-seller-signature", buyer_signature="legacy-buyer-signature"
        )
        before = swaps.filter(pk=tenant.swap.pk).values().get()
        reserved = list(orders.filter(pk__in=[before["sell_order_id"], before["buy_order_id"]]).order_by("pk").values())
        migrated = migrate_to(AFTER)
        row = migrated.get_model("tokens", "SwapOrder").objects.filter(pk=tenant.swap.pk).values().get()
        self.assertIs(row.pop("expiry_release_eligible"), False)
        self.assertEqual(row, before)
        self.assertEqual(
            list(
                migrated.get_model("tokens", "TransferOrder")
                .objects.filter(pk__in=[before["sell_order_id"], before["buy_order_id"]])
                .order_by("pk")
                .values()
            ),
            reserved,
        )
