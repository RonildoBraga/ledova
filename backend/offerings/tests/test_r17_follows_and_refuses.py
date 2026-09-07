from unittest import skipUnless

from django.db import connection
from django.test import TestCase, TransactionTestCase

from companies.models import Company, CompanyStatus, CompanyType
from companies.validators import acn_check_digit
from offerings.models import Offering
from offerings.models.offering import LIVE_OFFERING_STATUSES
from shared.constants import BLOCKCHAIN_BASE
from shared.tests.schema import migrate_to, restore_every_migration
from shared.tests.tenants import make_tenant
from tokens.models import ShareToken, ShareTokenStatus

POSTGRES = connection.vendor == "postgresql"
REASON = "the trigger is PostgreSQL only, and on SQLite none of these writes reaches a refusal"
SIBLING_SYMBOL = "SIB"
ONE_LIVE_PER_TOKEN = "offering_one_live_per_token"


def _unique_indexes_touching(table, column):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename = %s AND indexdef ILIKE '%%UNIQUE%%' "
            "AND indexdef LIKE %s",
            [table, f"%{column}%"],
        )
        return {name for (name,) in cursor.fetchall()}


def _acn(number):
    base = f"{number:08d}"
    return base + str(acn_check_digit(base))


def _company(owner, label, number):
    return Company.objects.create(
        owner=owner,
        name=f"{label} Pty Ltd",
        company_type=CompanyType.PROPRIETARY,
        acn=_acn(number),
        status=CompanyStatus.ACTIVE,
    )


def _token(company, symbol, tail):
    return ShareToken.objects.create(
        company=company,
        name=f"{symbol} class",
        symbol=symbol,
        total_supply="1000",
        status=ShareTokenStatus.DEPLOYED,
        contract_address="0x" + tail * 20,
        chain=BLOCKCHAIN_BASE,
    )


@skipUnless(POSTGRES, REASON)
class AnOfferingFollowsItsTokenAndWillNotChangeCompanyTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("r17offerings")
        self.other = make_tenant("r17offeringsother")
        self.offering = self.tenant.offering
        self.sibling = _token(self.tenant.company, SIBLING_SYMBOL, "71")

    def test_nothing_but_the_trigger_can_refuse_these_moves(self):
        clash = ShareToken.objects.filter(company=self.tenant.company, symbol=SIBLING_SYMBOL).exclude(
            pk=self.sibling.pk
        )
        self.assertFalse(clash.exists())

        for token in (self.sibling, self.other.deployed_token):
            with self.subTest(token=token.symbol):
                live = Offering.objects.filter(token=token, status__in=LIVE_OFFERING_STATUSES)
                self.assertFalse(live.exists())

        self.assertEqual(_unique_indexes_touching("offerings_offering", "token_id"), {ONE_LIVE_PER_TOKEN})
        self.assertEqual(_unique_indexes_touching("offerings_subscription", "offering_id"), set())

    def test_moving_an_offering_to_another_token_of_the_same_company_is_allowed(self):
        Offering.objects.filter(pk=self.offering.pk).update(token=self.sibling)

        self.offering.refresh_from_db()
        self.assertEqual(self.offering.token_id, self.sibling.uuid)
        self.assertEqual(self.offering.company_id, self.tenant.company.uuid)


@skipUnless(POSTGRES, REASON)
class AnOfferingWhoseTokenChangedCompanyIsNotWedgedTest(TransactionTestCase):

    def tearDown(self):
        restore_every_migration()
        super().tearDown()

    def test_the_old_refusal_is_back_after_the_reverse_and_gone_after_the_forward(self):
        tenant = make_tenant("r17stale")
        second = _company(tenant.user, "Second", 99000001)

        migrate_to([("offerings", "0005_r0_owner_columns")])
        ShareToken.objects.filter(pk=tenant.deployed_token.pk).update(company=second)
        with self.assertRaises(Exception) as wedged:
            Offering.objects.filter(pk=tenant.offering.pk).update(summary="renamed")
        self.assertIn("does not match its parent", str(wedged.exception))

        migrate_to([("offerings", "0006_trigger_follows_and_refuses")])
        Offering.objects.filter(pk=tenant.offering.pk).update(summary="renamed twice")
        tenant.offering.refresh_from_db()
        self.assertEqual(tenant.offering.company_id, second.uuid)
