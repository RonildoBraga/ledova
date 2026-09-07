from importlib import import_module
from unittest import skipUnless

from django.contrib.admin.sites import site
from django.db import connection, transaction
from django.test import RequestFactory, TestCase, TransactionTestCase

from companies.models import Company
from offerings.serializers.directory import DirectoryTokenListSerializer
from shared.tests.schema import migrate_to, restore_every_migration
from shared.tests.tenants import make_tenant
from tokens.models import ShareToken
from tokens.serializers.share_token import (
    ShareTokenCreateSerializer,
    ShareTokenDetailSerializer,
    ShareTokenListSerializer,
)

POSTGRES_ONLY = "The trigger is PostgreSQL; SQLite has no derive-and-refuse"
BEFORE_THE_OWNER_COLUMN = [("tokens", "0023_r0_owner_columns")]


class EveryTokenCarriesItsOwnerTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("token-owner")

    def test_a_token_carries_the_owner_of_the_company_that_issued_it(self):
        token = ShareToken.objects.get(pk=self.tenant.deployed_token.pk)

        self.assertEqual(token.owner_id, self.tenant.company.owner_id)

    def test_a_token_saved_without_an_owner_takes_its_company_s(self):
        token = ShareToken(
            company=self.tenant.company,
            name="Second class",
            symbol="SEC",
            total_supply="1000",
        )

        token.save()

        self.assertEqual(ShareToken.objects.get(pk=token.pk).owner_id, self.tenant.company.owner_id)


class TheOwnerColumnIsNotWritableThroughAnySerializerTest(TestCase):

    def test_no_serializer_over_share_token_exposes_the_owner_column(self):
        for serializer in (
            ShareTokenListSerializer,
            ShareTokenDetailSerializer,
            ShareTokenCreateSerializer,
            DirectoryTokenListSerializer,
        ):
            with self.subTest(serializer=serializer.__name__):
                self.assertNotIn("owner", serializer().fields)


@skipUnless(connection.vendor == "postgresql", POSTGRES_ONLY)
class TheTriggerRefusesAnOwnerTheCompanyDoesNotNameTest(TransactionTestCase):

    def setUp(self):
        super().setUp()
        self.tenant = make_tenant("token-trigger")
        self.stranger = make_tenant("token-stranger")

    def a_token(self, **overrides):
        fields = {
            "company": self.tenant.company,
            "name": "Trigger class",
            "symbol": "TRG",
            "total_supply": "500",
        }
        fields.update(overrides)
        return ShareToken(**fields)

    def test_a_token_inserted_with_no_owner_takes_the_company_s(self):
        token = self.a_token()

        ShareToken.objects.bulk_create([token])

        self.assertEqual(ShareToken.objects.get(pk=token.pk).owner_id, self.tenant.company.owner_id)

    def test_a_token_naming_an_owner_its_company_does_not_is_refused(self):
        with self.assertRaises(Exception) as refusal:
            with transaction.atomic():
                self.a_token(owner=self.stranger.company.owner).save()

        self.assertIn("does not match", str(refusal.exception))

    def transfer_the_company(self):
        company = self.tenant.company
        company.owner = self.stranger.company.owner
        company.save(update_fields=["owner"])
        return company.owner_id

    def test_an_ordinary_write_after_an_owner_transfer_is_not_refused(self):
        token = self.a_token()
        token.save()
        new_owner = self.transfer_the_company()

        ShareToken.objects.filter(pk=token.pk).update(name="Renamed after the transfer")

        self.assertEqual(ShareToken.objects.get(pk=token.pk).owner_id, new_owner)

    def test_a_stale_owner_is_re_derived_rather_than_refused(self):
        token = self.a_token()
        token.save()
        stale = token.owner_id
        new_owner = self.transfer_the_company()

        token.save(update_fields=["name"])

        self.assertNotEqual(stale, new_owner)
        self.assertEqual(ShareToken.objects.get(pk=token.pk).owner_id, new_owner)

    def test_following_the_parent_is_allowed(self):
        token = self.a_token()
        token.save()
        new_owner = self.transfer_the_company()

        ShareToken.objects.filter(pk=token.pk).update(owner_id=new_owner)

        self.assertEqual(ShareToken.objects.get(pk=token.pk).owner_id, new_owner)

    def test_a_token_cannot_be_moved_to_another_company(self):
        token = self.a_token(symbol="MOVE")
        token.save()

        with self.assertRaises(Exception) as refusal:
            with transaction.atomic():
                ShareToken.objects.filter(pk=token.pk).update(company=self.stranger.company)

        self.assertIn("cannot move this row to another owner", str(refusal.exception))
        self.assertEqual(ShareToken.objects.get(pk=token.pk).owner_id, self.tenant.company.owner_id)

    def test_a_token_may_move_between_two_companies_of_the_same_owner(self):
        token = self.a_token(symbol="MOVE")
        token.save()
        sibling = self.sibling_company()

        ShareToken.objects.filter(pk=token.pk).update(company=sibling)

        refreshed = ShareToken.objects.get(pk=token.pk)
        self.assertEqual(refreshed.company_id, sibling.pk)
        self.assertEqual(refreshed.owner_id, self.tenant.company.owner_id)

    def sibling_company(self):
        return Company.objects.create(
            owner=self.tenant.company.owner,
            name="Second company of the same owner",
            acn="000000489",
            status=self.tenant.company.status,
        )

    def test_neither_move_is_decided_by_the_unique_company_symbol(self):
        token = self.a_token(symbol="MOVE")
        token.save()

        for company in (self.stranger.company, self.sibling_company()):
            with self.subTest(company=company.name):
                taken = set(ShareToken.objects.filter(company=company).values_list("symbol", flat=True))
                self.assertNotIn(token.symbol, taken)

    def test_the_only_company_keyed_constraint_is_the_one_the_tests_control_for(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT conname FROM pg_constraint WHERE conrelid = 'tokens_sharetoken'::regclass "
                "AND contype IN ('u', 'x') AND pg_get_constraintdef(oid) LIKE %s",
                ["%company_id%"],
            )
            keyed = {name for (name,) in cursor.fetchall()}

        self.assertEqual(keyed, {"unique_company_symbol"})

    def test_a_token_stays_with_its_company_when_something_else_changes(self):
        token = self.a_token()
        token.save()

        ShareToken.objects.filter(pk=token.pk).update(name="Renamed")

        refreshed = ShareToken.objects.get(pk=token.pk)
        self.assertEqual(refreshed.company_id, self.tenant.company.pk)
        self.assertEqual(refreshed.owner_id, self.tenant.company.owner_id)

    def test_moving_the_row_to_someone_the_company_does_not_name_is_refused(self):
        token = self.a_token()
        token.save()

        with self.assertRaises(Exception) as refusal:
            with transaction.atomic():
                ShareToken.objects.filter(pk=token.pk).update(owner=self.stranger.company.owner)

        self.assertIn("cannot be moved to", str(refusal.exception))

    def test_the_column_is_not_nullable(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'tokens_sharetoken' AND column_name = 'owner_id'"
            )
            self.assertEqual(cursor.fetchone()[0], "NO")


@skipUnless(connection.vendor == "postgresql", POSTGRES_ONLY)
class TheMigrationRoundTripsOnPopulatedTablesTest(TransactionTestCase):

    def setUp(self):
        super().setUp()
        self.tenant = make_tenant("token-roundtrip")
        self.owner = self.tenant.company.owner_id
        self.addCleanup(restore_every_migration)

    def test_a_populated_token_table_survives_the_round_trip(self):
        migrate_to(BEFORE_THE_OWNER_COLUMN)
        restore_every_migration()

        self.assertEqual(ShareToken.objects.get(pk=self.tenant.deployed_token.pk).owner_id, self.owner)


class TheCompanyOwnerIsNotEditableOnAnExistingCompanyTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("admin-owner")
        self.admin = site._registry[Company]
        self.request = RequestFactory().get("/")
        self.request.user = self.tenant.user

    def test_an_existing_company_offers_its_owner_as_a_reading(self):
        self.assertIn("owner", self.admin.get_readonly_fields(self.request, obj=self.tenant.company))

    def test_the_add_form_still_asks_for_one(self):
        self.assertNotIn("owner", self.admin.get_readonly_fields(self.request, obj=None))


class TheReverseRestoresTheFunctionItReplacedTest(TestCase):

    @staticmethod
    def _body(module_name, constant):
        module = import_module(f"tokens.migrations.{module_name}")
        return getattr(module, constant)

    def test_the_reverse_body_is_the_one_0024_installed(self):
        installed = self._body("0024_r0_sharetoken_owner", "DERIVE_FUNCTION")
        restored = self._body("0025_a_token_cannot_change_company", "WITH_REPARENTING")

        self.assertEqual(restored, installed)

    def test_the_forward_body_differs_only_by_the_link_guard(self):
        without = self._body("0025_a_token_cannot_change_company", "WITHOUT_REPARENTING")
        with_it = self._body("0025_a_token_cannot_change_company", "WITH_REPARENTING")
        guard = (
            "        IF NEW.{parent_fk} IS DISTINCT FROM OLD.{parent_fk}\n"
            "           AND parent_owner_id IS DISTINCT FROM OLD.{column} THEN\n"
            "            RAISE EXCEPTION '{table} cannot move this row to another owner, from % to %',\n"
            "                OLD.{column}, parent_owner_id;\n"
            "        END IF;\n\n"
        )

        self.assertEqual(without.replace(guard, ""), with_it)
