from decimal import Decimal
from unittest import skipUnless

from django.conf import settings
from django.db import connection, transaction
from django.db.utils import ProgrammingError
from django.test import TestCase

from offerings.models import Subscription
from shared.db.principal import PRINCIPAL_SETTING
from shared.tests.tenants import make_tenant

POSTGRES = connection.vendor == "postgresql"
REASON = "the policies exist only in PostgreSQL, and without them both scopes return everything"


def a_subscription_from(buyer, offering):
    return Subscription.objects.create(
        offering=offering,
        user_account=buyer.account,
        wallet=buyer.wallet,
        submitted_by=buyer.user,
        quantity=3,
        price_per_share=Decimal("2.50"),
        amount_due=Decimal("7.50"),
    )


@skipUnless(POSTGRES, REASON)
class ATableReadAtTwoScopesHasARowWhereTheyDisagreeTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.issuer = make_tenant("twoscopeissuer")
        cls.buyer = make_tenant("twoscopebuyer")
        cls.crossing = a_subscription_from(cls.buyer, cls.issuer.offering)

    def as_the_app_role_for(self, user):
        self.addCleanup(self.back_to_the_owner)
        with connection.cursor() as cursor:
            cursor.execute(f"SET ROLE {settings.RLS_ROLES['app']}")
            cursor.execute("SELECT set_config(%s, %s, false)", [PRINCIPAL_SETTING, str(user.pk)])

    def back_to_the_owner(self):
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(f"RESET {PRINCIPAL_SETTING}")

    def test_the_fixture_holds_a_subscription_whose_buyer_does_not_own_the_offering(self):
        self.assertNotEqual(self.crossing.user_account_id, self.issuer.account.uuid)
        self.assertEqual(self.crossing.offering.company.owner_id, self.issuer.user.pk)

    def test_the_issuer_sees_a_subscription_from_an_account_that_is_not_theirs(self):
        self.as_the_app_role_for(self.issuer.user)

        self.assertIn(self.crossing, Subscription.objects.for_issuer(self.issuer.offering))

    def test_the_buyer_still_sees_their_own(self):
        self.as_the_app_role_for(self.buyer.user)

        self.assertIn(self.crossing, Subscription.objects.all())

    def test_a_third_party_sees_neither_scope(self):
        outsider = make_tenant("twoscopeoutsider")
        self.as_the_app_role_for(outsider.user)

        self.assertNotIn(self.crossing, Subscription.objects.all())

    def test_an_issuer_may_read_it_and_lock_it_and_still_not_write_it(self):
        self.as_the_app_role_for(self.issuer.user)

        self.assertEqual(Subscription.objects.select_for_update().filter(pk=self.crossing.pk).count(), 1)

        with self.assertRaises(ProgrammingError) as caught, transaction.atomic():
            Subscription.objects.filter(pk=self.crossing.pk).update(quantity=99)

        self.assertIn("row-level security policy", str(caught.exception))
