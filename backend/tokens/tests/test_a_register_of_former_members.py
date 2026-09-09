from datetime import date
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase

from ledova_backend.settings import base
from shared.db.policies import POLICIES
from shared.tests.tenants import make_tenant
from tokens.models import FormerHolder, ShareToken
from tokens.models.choices import IDENTITY_LABELS, IDENTITY_STAMPED, IDENTITY_UNKNOWN

POSTGRES_ONLY = "The derive-and-refuse trigger is PostgreSQL; SQLite has none"
POSTGRES = connection.vendor == "postgresql"
WALLET = "0x" + "ab" * 20


def a_cessation(token, wallet=WALLET, block=100, shares=1000, **fields):
    return FormerHolder.objects.create(
        token=token,
        wallet_address=wallet,
        ceased_on=date(2026, 3, 14),
        ceased_at_block=block,
        shares_at_cessation=shares,
        **fields,
    )


class AFormerMemberCarriesTheOwnerOfTheShareClassTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("former")
        self.token = self.tenant.deployed_token

    def test_a_row_saved_without_an_owner_takes_the_one_two_hops_up(self):
        row = a_cessation(self.token)

        self.assertEqual(row.owner_id, self.tenant.company.owner_id)
        self.assertEqual(self.token.company.owner_id, row.owner_id)

    def test_a_wallet_the_platform_never_identified_is_stamped_unknown_rather_than_left_blank(self):
        row = a_cessation(self.token)

        self.assertEqual(row.identity_source, IDENTITY_UNKNOWN)
        self.assertEqual(IDENTITY_LABELS[IDENTITY_UNKNOWN], "Never identified while it held shares")
        self.assertEqual((row.name, row.residential_address), ("", ""))

    def test_particulars_known_at_cessation_are_stamped_rather_than_joined_later(self):
        row = a_cessation(
            self.token,
            name="Bob Byer",
            residential_address="1 Example Street",
            identity_source=IDENTITY_STAMPED,
        )

        self.assertEqual((row.name, row.identity_source), ("Bob Byer", IDENTITY_STAMPED))

    def test_one_cessation_per_wallet_per_block_so_a_refold_writes_nothing_new(self):
        a_cessation(self.token)

        with self.assertRaises(IntegrityError), transaction.atomic():
            a_cessation(self.token)

    def test_a_wallet_that_ceased_twice_is_two_rows_because_it_rejoined_between_them(self):
        a_cessation(self.token, block=100)
        a_cessation(self.token, block=900)

        self.assertEqual(FormerHolder.objects.filter(wallet_address=WALLET).count(), 2)


class TheRetentionClockIsItsOwnTest(TestCase):

    def test_former_members_are_kept_seven_years_from_when_they_ceased(self):
        self.assertEqual(settings.FORMER_MEMBER_RETENTION_DAYS, 2557)

    def test_the_clock_reads_its_own_variable_rather_than_the_evidence_one_it_matches(self):
        source = Path(base.__file__).read_text()

        self.assertIn('os.environ.get("FORMER_MEMBER_RETENTION_DAYS", "2557")', source)
        self.assertEqual(settings.FORMER_MEMBER_RETENTION_DAYS, settings.CLASSIFICATION_EVIDENCE_RETENTION_DAYS)


class NobodyEditsAStatutoryRecordThroughTheApiTest(TestCase):

    def test_the_read_term_is_the_owner_and_carries_no_market_term(self):
        readable, writable = POLICIES["tokens_formerholder"]

        self.assertIn("owner_id =", readable)
        self.assertNotIn("OR", readable)
        self.assertNotIn("on_the_market", readable.lower())

    def test_the_app_role_writes_nothing(self):
        _, writable = POLICIES["tokens_formerholder"]

        self.assertEqual(writable, "false")

    def test_the_share_class_above_it_does_carry_the_market_term_which_is_the_point(self):
        readable, _ = POLICIES["tokens_sharetoken"]

        self.assertIn("OR", readable)


@skipUnless(POSTGRES, POSTGRES_ONLY)
class TheTriggerDerivesAndRefusesTest(TransactionTestCase):

    def setUp(self):
        super().setUp()
        self.tenant = make_tenant("formertrigger")
        self.other = make_tenant("formerelsewhere")
        self.token = self.tenant.deployed_token
        self.sibling = self.a_sibling_class()

    def a_sibling_class(self):
        sibling = ShareToken.objects.get(pk=self.token.pk)
        sibling.pk = None
        sibling.uuid = None
        sibling.symbol = "SIB"
        sibling.contract_address = "0x" + "7" * 40
        sibling.save()
        return sibling

    def test_the_policy_the_catalogue_declares_is_the_one_the_database_has(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT policyname, cmd, qual, with_check FROM pg_policies "
                "WHERE tablename = 'tokens_formerholder' ORDER BY policyname"
            )
            installed = {row[0]: (row[1], row[2], row[3]) for row in cursor.fetchall()}

        self.assertEqual(
            set(installed),
            {
                "tokens_formerholder_read",
                "tokens_formerholder_insert",
                "tokens_formerholder_update",
                "tokens_formerholder_delete",
            },
        )
        self.assertIn("owner_id", installed["tokens_formerholder_read"][1])
        self.assertNotIn("on_the_market", (installed["tokens_formerholder_read"][1] or "").lower())
        self.assertEqual(installed["tokens_formerholder_insert"][2], "false")
        self.assertEqual(installed["tokens_formerholder_delete"][1], "false")

    def test_row_level_security_is_on_and_forced_for_the_table(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'tokens_formerholder'"
            )
            enabled, forced = cursor.fetchone()

        self.assertEqual((enabled, forced), (True, True))

    def test_an_owner_that_does_not_match_the_share_class_is_refused_on_insert(self):
        with self.assertRaises(Exception) as refusal, transaction.atomic():
            FormerHolder.objects.create(
                token=self.token,
                owner=self.other.user,
                wallet_address=WALLET,
                ceased_on=date(2026, 3, 14),
                ceased_at_block=100,
                shares_at_cessation=1000,
            )

        self.assertIn("does not match the owner of", str(refusal.exception))

    def test_moving_a_row_to_another_company_s_share_class_is_refused(self):
        row = a_cessation(self.token)

        with self.assertRaises(Exception) as refusal, transaction.atomic():
            FormerHolder.objects.filter(pk=row.pk).update(token=self.other.deployed_token)

        self.assertIn("cannot move this row to another owner", str(refusal.exception))

    def test_moving_a_row_between_share_classes_of_the_same_company_is_allowed(self):
        row = a_cessation(self.token)

        FormerHolder.objects.filter(pk=row.pk).update(token=self.sibling)

        row.refresh_from_db()
        self.assertEqual((row.token_id, row.owner_id), (self.sibling.uuid, self.tenant.company.owner_id))
