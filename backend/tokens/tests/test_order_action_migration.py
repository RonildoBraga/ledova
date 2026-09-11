from unittest import skipUnless

from django.conf import settings
from django.test import TransactionTestCase

from shared.tests.schema import migrate_to, restore_every_migration
from shared.tests.tenants import make_tenant
from tokens.tests.order_action_fixtures import OWNER, legacy_action_values

_migration_modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("tokens" in _migration_modules and _migration_modules["tokens"] is None)


@skipUnless(MIGRATIONS_ENABLED, "Requires actual order action migrations")
class OrderActionMigrationPreservesLegacyHistoryTest(TransactionTestCase):
    def test_legacy_pending_spent_and_audit_bytes_survive_without_invented_actions(self):
        tenant = make_tenant("action-migration")
        before = migrate_to([("tokens", "0037_order_submissions")])
        self.addCleanup(restore_every_migration)
        before.get_model("wallets", "Wallet").objects.filter(pk=tenant.wallet.pk).update(address=OWNER.address)
        before.get_model("tokens", "TransferOrder").objects.filter(pk=tenant.order.pk).update(
            wallet_address=OWNER.address
        )
        challenges = before.get_model("tokens", "SigningChallenge").objects
        logs = before.get_model("tokens", "OrderModificationLog").objects
        swaps = before.get_model("tokens", "SwapOrder").objects
        settlement = swaps.filter(pk=tenant.swap.pk).values().get()
        originals = []
        audit = None
        for purpose in ("cancel", "modify"):
            for consumed in (False, True):
                values, signature = legacy_action_values(tenant.order, OWNER, purpose, 311 + len(originals), consumed)
                challenge = challenges.create(**values)
                originals.append(challenges.filter(pk=challenge.pk).values().get())
                if purpose == "modify" and consumed:
                    log = logs.create(
                        order_id=tenant.order.pk,
                        challenge_id=challenge.pk,
                        field_name="quantity",
                        old_value="10",
                        new_value="12",
                        signature=signature,
                        signer_address=OWNER.address,
                    )
                    audit = logs.filter(pk=log.pk).values().get()
        after = migrate_to([("tokens", "0038_order_action_submissions")])
        for original in originals:
            current = after.get_model("tokens", "SigningChallenge").objects.filter(pk=original["uuid"]).values().get()
            self.assertIsNone(current.pop("action_id"))
            self.assertEqual(current, original)
        self.assertEqual(
            after.get_model("tokens", "OrderModificationLog").objects.filter(pk=audit["uuid"]).values().get(), audit
        )
        self.assertEqual(
            after.get_model("tokens", "SwapOrder").objects.filter(pk=tenant.swap.pk).values().get(), settlement
        )
        self.assertEqual(after.get_model("tokens", "OrderActionSubmission").objects.count(), 0)
