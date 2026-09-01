"""Isolated PostgreSQL proof for the proposed tenant RLS policy shape.

The test creates a unique, non-login role and temporary policies inside the
test database, exercises them, and removes every role, grant, policy, and
session setting afterward. The application ships no runtime RLS migration or
role provisioning.
"""

import uuid
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection
from django.test import SimpleTestCase, TransactionTestCase

from portfolios.models import Portfolio
from tenancy.policy_sql import (
    CORE_TENANT_TABLES,
    disable_policy_sql,
    enable_policy_sql,
)
from users.models import UserAccount, UserProfile
from wallets.models import Wallet

User = get_user_model()


class PolicySQLSafetyTest(SimpleTestCase):
    def test_helpers_reject_unsafe_identifiers(self):
        unsafe_calls = [
            lambda: enable_policy_sql("wallets;drop_table", "user_account_id"),
            lambda: enable_policy_sql("wallets", "user-account-id"),
            lambda: enable_policy_sql("wallets", "user_account_id", "policy name"),
            lambda: disable_policy_sql("public.wallets"),
            lambda: disable_policy_sql("wallets", "policy;drop"),
        ]

        for unsafe_call in unsafe_calls:
            with self.subTest(call=unsafe_call):
                with self.assertRaisesRegex(ValueError, "simple lowercase PostgreSQL identifier"):
                    unsafe_call()


@skipUnless(connection.vendor == "postgresql", "RLS is a PostgreSQL feature")
class RLSEnforcementTest(TransactionTestCase):
    reset_sequences = False

    @classmethod
    def _sql(cls, statement, params=None, fetchone=False):
        with connection.cursor() as cursor:
            cursor.execute(statement, params or [])
            return cursor.fetchone() if fetchone else None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        suffix = uuid.uuid4().hex[:12]
        cls.role_name = f"rls_proof_{suffix}"
        cls.policy_name = f"tenant_isolation_proof_{suffix}"
        cls.quoted_role = connection.ops.quote_name(cls.role_name)
        cls.current_user = cls._sql("SELECT current_user", fetchone=True)[0]
        quoted_current_user = connection.ops.quote_name(cls.current_user)
        cls.rls_was_enabled = {}

        for table, _owner_column in CORE_TENANT_TABLES:
            cls.rls_was_enabled[table] = cls._sql(
                "SELECT relrowsecurity FROM pg_class WHERE oid = to_regclass(%s)",
                [table],
                fetchone=True,
            )[0]

        cls._sql(
            f"CREATE ROLE {cls.quoted_role} "
            "NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOINHERIT NOREPLICATION NOBYPASSRLS"
        )
        cls.addClassCleanup(cls._cleanup_proof_state)
        cls._sql(f"GRANT {cls.quoted_role} TO {quoted_current_user}")
        cls._sql(f"GRANT USAGE ON SCHEMA public TO {cls.quoted_role}")
        cls._sql(f"GRANT SELECT, UPDATE ON TABLE wallets TO {cls.quoted_role}")
        cls._sql(f"GRANT SELECT ON TABLE portfolios TO {cls.quoted_role}")

        for table, owner_column in CORE_TENANT_TABLES:
            cls._sql(enable_policy_sql(table, owner_column, cls.policy_name))

    @classmethod
    def _cleanup_proof_state(cls):
        failures = []

        def attempt(statement):
            try:
                cls._sql(statement)
            except Exception as exc:
                failures.append(exc)

        attempt("RESET ROLE")
        attempt("RESET app.account_ids")

        for table, _owner_column in CORE_TENANT_TABLES:
            if cls.rls_was_enabled.get(table) is False:
                attempt(disable_policy_sql(table, cls.policy_name))
            else:
                attempt(f"DROP POLICY IF EXISTS {cls.policy_name} ON {table}")

        for table, _owner_column in CORE_TENANT_TABLES:
            attempt(f"REVOKE ALL PRIVILEGES ON TABLE {table} FROM {cls.quoted_role}")
        attempt(f"REVOKE USAGE ON SCHEMA public FROM {cls.quoted_role}")
        attempt(f"REVOKE {cls.quoted_role} " f"FROM {connection.ops.quote_name(cls.current_user)}")
        attempt(f"DROP ROLE {cls.quoted_role}")

        if failures:
            raise AssertionError("RLS proof cleanup did not complete") from failures[0]

    def setUp(self):
        self.acc_a, self.wallet_a, self.portfolio_a = self._make_tenant(
            "a@ex.com",
            "0x" + "a" * 40,
            "A portfolio",
        )
        self.acc_b, self.wallet_b, self.portfolio_b = self._make_tenant(
            "b@ex.com",
            "0x" + "b" * 40,
            "B portfolio",
        )

    def tearDown(self):
        self._reset_role()
        super().tearDown()

    def _make_tenant(self, email, address, portfolio_name):
        user = User.objects.create_user(email=email)
        profile = UserProfile.objects.create(user=user)
        account = UserAccount.objects.create()
        account.user_profiles.add(profile)
        wallet = Wallet.objects.create(
            user_account=account,
            address=address,
            chain="ethereum",
            custody_model="non_custodial",
            wallet_type="software",
            verification_status="PENDING",
        )
        portfolio = Portfolio.objects.create(user_account=account, name=portfolio_name)
        return account, wallet, portfolio

    def _as_proof_role(self, account_ids=None):
        self._sql(f"SET ROLE {self.quoted_role}")
        if account_ids is None:
            self._sql("RESET app.account_ids")
        else:
            self._sql("SET app.account_ids = %s", [account_ids])

    def _reset_role(self):
        self._sql("RESET ROLE")
        self._sql("RESET app.account_ids")

    def test_role_is_non_login_non_superuser_without_rls_bypass(self):
        attributes = self._sql(
            "SELECT rolcanlogin, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = %s",
            [self.role_name],
            fetchone=True,
        )
        self.assertEqual(attributes, (False, False, False))

    def test_unscoped_queries_return_only_current_tenant(self):
        self._as_proof_role(str(self.acc_b.pk))

        wallet_ids = set(Wallet.objects.all().values_list("uuid", flat=True))
        portfolio_ids = set(Portfolio.objects.all().values_list("uuid", flat=True))

        self.assertEqual(wallet_ids, {self.wallet_b.pk})
        self.assertEqual(portfolio_ids, {self.portfolio_b.pk})

    def test_multiple_account_ids_return_their_combined_rows(self):
        self._as_proof_role(f"{self.acc_a.pk},{self.acc_b.pk}")

        wallet_ids = set(Wallet.objects.all().values_list("uuid", flat=True))
        portfolio_ids = set(Portfolio.objects.all().values_list("uuid", flat=True))

        self.assertEqual(wallet_ids, {self.wallet_a.pk, self.wallet_b.pk})
        self.assertEqual(portfolio_ids, {self.portfolio_a.pk, self.portfolio_b.pk})

    def test_unset_and_empty_settings_fail_closed(self):
        self._as_proof_role()
        self.assertEqual(Wallet.objects.all().count(), 0)
        self.assertEqual(Portfolio.objects.all().count(), 0)

        self._sql("SET app.account_ids = ''")
        self.assertEqual(Wallet.objects.all().count(), 0)
        self.assertEqual(Portfolio.objects.all().count(), 0)

    def test_same_tenant_update_succeeds_then_cross_tenant_update_is_rejected(self):
        self._as_proof_role(str(self.acc_b.pk))

        self._sql(
            "UPDATE wallets SET verification_status = %s WHERE uuid = %s",
            ["VERIFIED", self.wallet_b.pk],
        )
        self.wallet_b.refresh_from_db()
        self.assertEqual(self.wallet_b.verification_status, "VERIFIED")

        with self.assertRaises(DatabaseError) as raised:
            self._sql(
                "UPDATE wallets SET user_account_id = %s WHERE uuid = %s",
                [self.acc_a.pk, self.wallet_b.pk],
            )

        cause = raised.exception.__cause__
        sqlstate = getattr(cause, "sqlstate", None) or getattr(cause, "pgcode", None)
        self.assertEqual(sqlstate, "42501")

    def test_owner_connection_bypasses_proof_policies(self):
        self._reset_role()
        self.assertEqual(Wallet.objects.all().count(), 2)
        self.assertEqual(Portfolio.objects.all().count(), 2)

    def test_policy_table_names_match_models(self):
        self.assertEqual(
            set(CORE_TENANT_TABLES),
            {
                (Wallet._meta.db_table, "user_account_id"),
                (Portfolio._meta.db_table, "user_account_id"),
            },
        )
