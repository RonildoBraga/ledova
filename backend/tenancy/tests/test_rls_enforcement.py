"""Prove RLS blocks cross-tenant reads/writes at the database layer.

Test migrations are disabled in the test settings, so the policies from the
tenancy migration are not present in the test DB. This test applies the same
policy SQL itself (via tenancy.policy_sql, the single source of truth), then
runs deliberately UNSCOPED ORM queries (Wallet.objects.all(), bypassing the
guardian read filter) as the non-superuser app_user role. If RLS is working,
the database returns only the current tenant's rows regardless of what the ORM
asked for.
"""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase
from unittest import skipUnless

from tenancy.policy_sql import enable_policy_sql
from users.models import UserAccount, UserProfile
from wallets.models import Wallet

User = get_user_model()

APP_ROLE = "app_user"


@skipUnless(connection.vendor == "postgresql", "RLS is a PostgreSQL feature")
class RLSEnforcementTest(TransactionTestCase):
    reset_sequences = False

    def _sql(self, statement, params=None):
        with connection.cursor() as c:
            c.execute(statement, params or [])

    def _make_tenant(self, email, address):
        user = User.objects.create_user(email=email, password="pw-12345678")
        profile = UserProfile.objects.create(user=user)
        account = UserAccount.objects.create()
        account.user_profiles.add(profile)
        wallet = Wallet.objects.create(
            user_account=account, address=address, chain="ethereum",
            custody_model="non_custodial", wallet_type="software", verification_status="PENDING",
        )
        return account, wallet

    def setUp(self):
        # Provision the role + policy directly (migrations are disabled in tests).
        self._sql(
            "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname=%s) "
            "THEN CREATE ROLE app_user NOLOGIN; END IF; END $$;",
            [APP_ROLE],
        )
        self._sql("GRANT USAGE ON SCHEMA public TO app_user;")
        self._sql("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;")
        self._sql("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;")
        # Let the (superuser) test connection SET ROLE to app_user.
        self._sql("GRANT app_user TO CURRENT_USER;")
        for stmt in enable_policy_sql("wallets", "user_account_id").split(";"):
            if stmt.strip():
                self._sql(stmt)

        self.acc_a, self.wallet_a = self._make_tenant("a@ex.com", "0x" + "a" * 40)
        self.acc_b, self.wallet_b = self._make_tenant("b@ex.com", "0x" + "b" * 40)

    def tearDown(self):
        self._sql("RESET ROLE;")
        self._sql("RESET app.account_ids;")
        self._sql("ALTER TABLE wallets DISABLE ROW LEVEL SECURITY;")
        self._sql("DROP POLICY IF EXISTS tenant_isolation ON wallets;")

    def _as_app_user(self, account_ids):
        self._sql("SET ROLE app_user;")
        self._sql("SET app.account_ids = %s;", [account_ids])

    def test_unscoped_query_returns_only_current_tenant(self):
        self._as_app_user(str(self.acc_b.pk))
        # NOTE: .all(), NOT visible_to_user() — the ORM is told to fetch everything.
        addresses = set(Wallet.objects.all().values_list("address", flat=True))
        self.assertEqual(addresses, {self.wallet_b.address})
        self.assertNotIn(self.wallet_a.address, addresses)

    def test_unset_variable_fails_closed(self):
        self._sql("SET ROLE app_user;")
        self._sql("RESET app.account_ids;")
        self.assertEqual(Wallet.objects.all().count(), 0)

    def test_cannot_write_row_for_another_tenant(self):
        from django.db import IntegrityError, InternalError, ProgrammingError

        self._as_app_user(str(self.acc_b.pk))
        with self.assertRaises((IntegrityError, InternalError, ProgrammingError)):
            Wallet.objects.create(
                user_account_id=self.acc_a.pk, address="0x" + "c" * 40, chain="ethereum",
                custody_model="non_custodial", wallet_type="software", verification_status="PENDING",
            )

    def test_owner_connection_bypasses_rls(self):
        # Sanity: as the owner (no SET ROLE) all rows are visible — proves the
        # test is exercising the role boundary, not a blanket empty result.
        self.assertEqual(Wallet.objects.all().count(), 2)
