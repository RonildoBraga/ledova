from unittest import skipUnless

from django.conf import settings
from django.db import connection, transaction
from django.test import TestCase

from companies.models import Company
from offerings.models import Subscription
from portfolios.models import Portfolio
from shared.db.principal import PRINCIPAL_SETTING
from shared.tests.tenants import make_tenant
from tokens.models import ShareToken
from users.models import UserAccount, UserPreferences
from wallets.models import Transaction, Wallet

POSTGRES = connection.vendor == "postgresql"
REASON = "row-level security exists only in PostgreSQL, and on SQLite every assertion here would pass unscoped"


@skipUnless(POSTGRES, REASON)
class ThePolicyScopesWhatTheQuerysetScopedTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.one = make_tenant("rlsone")
        cls.two = make_tenant("rlstwo")

    def as_the_app_role_for(self, user):
        self.addCleanup(self.back_to_the_owner)
        with connection.cursor() as cursor:
            cursor.execute(f"SET ROLE {settings.RLS_ROLES['app']}")
            cursor.execute("SELECT set_config(%s, %s, false)", [PRINCIPAL_SETTING, str(user.pk)])

    def back_to_the_owner(self):
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute("SELECT set_config(%s, NULL, false)", [PRINCIPAL_SETTING])

    def test_the_owner_sees_both_tenants_before_any_role_is_taken(self):
        self.assertIn(self.one.company, Company.objects.all())
        self.assertIn(self.two.company, Company.objects.all())

    def _withdraw_from_the_market(self, tenant):
        ShareToken.objects.filter(company=tenant.company).update(status="draft", contract_address=None)
        Company.objects.filter(pk=tenant.company.pk).update(is_open_to_investors=False)

    def test_a_company_that_has_published_nothing_is_invisible_to_another_principal(self):
        self._withdraw_from_the_market(self.two)
        self.as_the_app_role_for(self.one.user)

        self.assertEqual(list(Company.objects.all()), [self.one.company])

    def test_the_same_query_under_the_other_principal_returns_the_other_tenant(self):
        self._withdraw_from_the_market(self.one)
        self.as_the_app_role_for(self.two.user)

        self.assertEqual(list(Company.objects.all()), [self.two.company])

    def test_a_company_with_a_token_on_the_market_is_visible_to_every_principal(self):
        self.as_the_app_role_for(self.one.user)

        self.assertIn(self.two.company, Company.objects.all())

    def test_an_account_member_table_is_scoped_without_its_queryset(self):
        self.as_the_app_role_for(self.one.user)

        visible = {wallet.uuid for wallet in Wallet.objects.all()}
        self.assertIn(self.one.wallet.uuid, visible)
        self.assertNotIn(self.two.spare_wallet.uuid, visible)

        self.assertEqual({row.user_account_id for row in Transaction.objects.all()}, {self.one.account.uuid})
        self.assertEqual({row.user_account_id for row in Portfolio.objects.all()}, {self.one.account.uuid})
        self.assertIn(self.one.account, UserAccount.objects.all())

    def test_a_wallet_that_signs_for_a_company_is_visible_to_every_principal(self):
        self.as_the_app_role_for(self.one.user)

        self.assertIn(self.two.wallet.uuid, {wallet.uuid for wallet in Wallet.objects.all()})
        self.assertIn(self.two.account, UserAccount.objects.all())

    def test_a_profile_owned_table_is_scoped_by_the_column_r0_added(self):
        self.as_the_app_role_for(self.one.user)

        self.assertEqual({row.user_id for row in UserPreferences.objects.all()}, {self.one.user.pk})

    def test_a_company_derived_table_is_scoped_through_the_helper(self):
        self.as_the_app_role_for(self.one.user)

        self.assertNotEqual(list(Subscription.objects.all()), [])
        self.assertEqual({row.user_account_id for row in Subscription.objects.all()}, {self.one.account.uuid})

    def test_a_write_for_another_tenant_is_refused_rather_than_hidden(self):
        self.as_the_app_role_for(self.one.user)

        with self.assertRaises(Exception), transaction.atomic():
            Wallet.objects.create(user_account=self.two.account, address="0x" + "e" * 40, chain="base")

    def test_a_query_with_no_principal_raises_rather_than_returning_nothing(self):
        with connection.cursor() as cursor:
            cursor.execute(f"SET ROLE {settings.RLS_ROLES['app']}")
        self.addCleanup(self.back_to_the_owner)

        with self.assertRaises(Exception), transaction.atomic():
            list(Company.objects.all())
