from decimal import Decimal
from importlib import import_module

from django.db import IntegrityError, ProgrammingError, connection, transaction
from django.test import TestCase

from offerings.models import Offering, Subscription
from shared.tests.tenants import make_tenant

POSTGRES_ONLY = (
    "The derive-and-refuse trigger is PostgreSQL only: SQLite has no plpgsql, and the column exists "
    "for a PostgreSQL row-level security policy, so there is nothing on SQLite for it to protect."
)


class OwnerColumnIsDerivedInPythonTest(TestCase):

    def setUp(self):
        self.issuer = make_tenant("issuer")

    def test_an_offering_carries_its_tokens_company_without_being_told(self):
        self.assertEqual(self.issuer.offering.company_id, self.issuer.offering.token.company_id)

    def test_a_subscription_carries_its_offerings_company_without_being_told(self):
        self.assertEqual(self.issuer.subscription.company_id, self.issuer.offering.company_id)

    def test_a_subscription_derives_from_the_offering_not_from_the_token(self):
        subscription = Subscription.objects.get(pk=self.issuer.subscription.pk)

        self.assertEqual(subscription.company_id, subscription.offering.company_id)

    def test_an_explicit_company_is_left_alone(self):
        offering = Offering.objects.get(pk=self.issuer.offering.pk)
        offering.pk = None
        offering._state.adding = True
        offering.company = self.issuer.company
        offering.save()

        self.assertEqual(offering.company_id, self.issuer.company.pk)

    def test_the_column_is_not_in_any_api_representation(self):
        from offerings.serializers.offering import (
            OfferingListSerializer,
            OfferingWriteSerializer,
        )
        from offerings.serializers.subscription import (
            IssuerSubscriptionSerializer,
            SubscriptionCreateSerializer,
            SubscriptionListSerializer,
        )

        for serializer in (
            OfferingListSerializer,
            OfferingWriteSerializer,
            IssuerSubscriptionSerializer,
            SubscriptionCreateSerializer,
            SubscriptionListSerializer,
        ):
            with self.subTest(serializer=serializer.__name__):
                self.assertNotIn("company", serializer().fields)


class DerivationOrderTest(TestCase):

    def test_a_parent_is_backfilled_before_its_child(self):
        module = import_module("offerings.migrations.0005_r0_owner_columns")
        position = {name: index for index, (name, _, _) in enumerate(module.DERIVATIONS)}

        for name, _, (app, parent) in module.DERIVATIONS:
            if parent in position:
                with self.subTest(child=name, parent=parent):
                    self.assertEqual(app, "offerings")
                    self.assertLess(position[parent], position[name])


class OwnerColumnTriggerTest(TestCase):

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest(POSTGRES_ONLY)
        self.issuer = make_tenant("issuer")
        self.stranger = make_tenant("stranger")

    def _rows(self):
        return (
            (Offering, self.issuer.offering),
            (Subscription, self.issuer.subscription),
        )

    def test_bulk_create_bypasses_the_python_half_and_the_trigger_derives(self):
        row = Subscription(
            offering=self.issuer.offering,
            user_account=self.issuer.account,
            wallet=self.issuer.wallet,
            submitted_by=self.issuer.user,
            quantity=1,
            price_per_share=Decimal("2.50"),
            amount_due=Decimal("2.50"),
        )
        Subscription.objects.bulk_create([row])

        self.assertEqual(Subscription.objects.get(pk=row.pk).company_id, self.issuer.offering.company_id)

    def test_a_mismatched_company_is_refused(self):
        for model, row in self._rows():
            with self.subTest(model=model.__name__):
                with self.assertRaises((IntegrityError, ProgrammingError)) as raised:
                    with transaction.atomic(), connection.cursor() as cursor:
                        cursor.execute(
                            f'UPDATE "{model._meta.db_table}" SET company_id = %s WHERE uuid = %s',
                            [self.stranger.company.pk, row.pk],
                        )

                self.assertIn("does not match its parent", str(raised.exception))

    def test_moving_a_row_to_another_companys_parent_is_refused(self):
        cases = (
            (Offering, self.issuer.offering, "token_id", self.stranger.offering.token_id),
            (Subscription, self.issuer.subscription, "offering_id", self.stranger.offering.pk),
        )
        for model, row, column, foreign in cases:
            with self.subTest(model=model.__name__):
                with self.assertRaises((IntegrityError, ProgrammingError)) as raised:
                    with transaction.atomic(), connection.cursor() as cursor:
                        cursor.execute(
                            f'UPDATE "{model._meta.db_table}" SET {column} = %s WHERE uuid = %s',
                            [foreign, row.pk],
                        )

                self.assertIn("does not match its parent", str(raised.exception))

    def test_changing_the_parent_and_the_company_together_is_still_refused(self):
        with self.assertRaises((IntegrityError, ProgrammingError)) as raised:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(
                    f'UPDATE "{Subscription._meta.db_table}" SET offering_id = %s, company_id = %s WHERE uuid = %s',
                    [self.stranger.offering.pk, self.stranger.company.pk, self.issuer.subscription.pk],
                )

        self.assertIn("company_id cannot change", str(raised.exception))

    def test_nulling_the_company_is_repaired_rather_than_refused(self):
        for model, row in self._rows():
            with self.subTest(model=model.__name__):
                with connection.cursor() as cursor:
                    cursor.execute(f'UPDATE "{model._meta.db_table}" SET company_id = NULL WHERE uuid = %s', [row.pk])

                row.refresh_from_db()
                self.assertIsNotNone(row.company_id)

    def test_the_column_is_not_null_which_is_what_makes_the_fill_guard_unreachable(self):
        for model, _ in self._rows():
            with self.subTest(model=model.__name__), connection.cursor() as cursor:
                cursor.execute(
                    "SELECT is_nullable FROM information_schema.columns " "WHERE table_name = %s AND column_name = %s",
                    [model._meta.db_table, model._meta.get_field("company").column],
                )

                self.assertEqual(cursor.fetchone()[0], "NO")

    def test_an_ordinary_update_still_works(self):
        offering = self.issuer.offering

        offering.summary = "Reworded"
        offering.save(update_fields=["summary"])
        offering.refresh_from_db()

        self.assertEqual(offering.summary, "Reworded")
        self.assertEqual(offering.company_id, offering.token.company_id)
