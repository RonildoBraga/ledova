from unittest import skipUnless

from django.conf import settings
from django.db import IntegrityError, transaction
from django.test import TransactionTestCase

from shared.tests.schema import migrate_to, restore_every_migration
from shared.tests.tenants import make_tenant
from tokens.models import ShareToken

BEFORE = [("tokens", "0029_execution_notes")]
AFTER = [("tokens", "0031_share_tokens_have_zero_decimals")]
_migration_modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("tokens" in _migration_modules and _migration_modules["tokens"] is None)


@skipUnless(MIGRATIONS_ENABLED, "Requires actual token migrations")
class WholeShareMigrationTest(TransactionTestCase):

    def test_nonzero_legacy_values_stop_migration_until_an_operator_corrects_them(self):
        token = make_tenant("legacy-share").token

        def restore():
            ShareToken.objects.filter(pk=token.pk).update(decimals=0)
            restore_every_migration()

        self.addCleanup(restore)
        historical = migrate_to(BEFORE).get_model("tokens", "ShareToken")
        historical.objects.filter(pk=token.pk).update(decimals=18)

        with self.assertRaisesRegex(RuntimeError, str(token.uuid)) as caught:
            migrate_to(AFTER)

        self.assertIn("decimals=18", str(caught.exception))
        self.assertEqual(historical.objects.get(pk=token.pk).decimals, 18)

        historical.objects.filter(pk=token.pk).update(decimals=0)
        migrated = migrate_to(AFTER).get_model("tokens", "ShareToken")
        self.assertEqual(migrated.objects.get(pk=token.pk).decimals, 0)
        with self.assertRaises(IntegrityError), transaction.atomic():
            migrated.objects.filter(pk=token.pk).update(decimals=1)

        reversed_model = migrate_to(BEFORE).get_model("tokens", "ShareToken")
        self.assertEqual(reversed_model.objects.get(pk=token.pk).decimals, 0)
