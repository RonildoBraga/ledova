from contextlib import contextmanager
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import ProgrammingError, connections
from django.test import TestCase
from rest_framework.test import APITransactionTestCase

from companies.identity import company_identity
from companies.models import (
    Company,
    CompanyRegistryCheck,
    CompanyStatus,
    RegistryCheckPurpose,
)
from companies.services import transition_company
from companies.tests.registry_fixtures import matching_observation
from shared.db import atomic, current_alias, use_operator
from shared.db.principal import PRINCIPAL_SETTING
from shared.tests.scoped import RunsOnTheScopedConnection
from tokens.models import ShareToken


@skipUnless(connections[current_alias()].vendor == "postgresql", "Registry history RLS requires PostgreSQL")
class RegistryHistoryIsOperatorOnlyTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(email="registry-policy-owner@example.test")
        cls.other = User.objects.create_user(email="registry-policy-other@example.test")
        cls.company = Company.objects.create(
            owner=cls.owner,
            name="Registry Policy Pty Ltd",
            acn="123456780",
            status=CompanyStatus.ACTIVE,
            is_open_to_investors=True,
        )
        cls.fields = dict(
            company=cls.company,
            purpose=RegistryCheckPurpose.RETRY,
            requested_name=cls.company.name,
            requested_acn=cls.company.acn,
            requested_abn="",
            identity=company_identity(cls.company),
            lifecycle_revision=0,
        )
        cls.check = CompanyRegistryCheck.objects.create(**cls.fields)

    @contextmanager
    def as_app(self, user):
        connection = connections[current_alias()]
        with connection.cursor() as cursor:
            cursor.execute(f"SET ROLE {settings.RLS_ROLES['app']}")
            cursor.execute("SELECT set_config(%s, %s, false)", [PRINCIPAL_SETTING, str(user.pk) if user else ""])
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
                cursor.execute("SELECT set_config(%s, NULL, false)", [PRINCIPAL_SETTING])

    def test_history_is_hidden_from_the_owner_and_from_an_investor(self):
        self.assertEqual(list(CompanyRegistryCheck.objects.all()), [self.check])
        for user in (self.owner, self.other):
            with self.subTest(user=user), self.as_app(user):
                self.assertTrue(Company.objects.filter(pk=self.company.pk).exists())
                self.assertFalse(CompanyRegistryCheck.objects.exists())
                self.assertFalse(CompanyRegistryCheck.objects.select_for_update().exists())
        self.assertEqual(list(CompanyRegistryCheck.objects.all()), [self.check])

    def test_a_connection_with_no_principal_reaches_neither_the_history_nor_the_company(self):
        self.assertEqual(list(CompanyRegistryCheck.objects.all()), [self.check])
        with self.as_app(None):
            self.assertFalse(CompanyRegistryCheck.objects.exists())
            self.assertFalse(Company.objects.filter(pk=self.company.pk).exists())
        self.assertEqual(list(CompanyRegistryCheck.objects.all()), [self.check])

    def test_an_owner_cannot_insert_update_or_delete_registry_evidence(self):
        with self.as_app(self.owner):
            with self.assertRaisesMessage(ProgrammingError, "row-level security"):
                with atomic():
                    CompanyRegistryCheck.objects.create(**self.fields)
            self.assertEqual(CompanyRegistryCheck.objects.filter(pk=self.check.pk).update(status="passed"), 0)
            self.assertEqual(CompanyRegistryCheck.objects.filter(pk=self.check.pk).delete()[0], 0)
        self.check.refresh_from_db()
        self.assertEqual(self.check.status, "pending")
        self.assertEqual(CompanyRegistryCheck.objects.filter(pk=self.check.pk).update(status="passed"), 1)


class ReviewedCompanyDeletionOnScopedConnectionTest(RunsOnTheScopedConnection, APITransactionTestCase):
    def setUp(self):
        with use_operator():
            User = get_user_model()
            self.owner = User.objects.create_user(email="registry-delete-owner@example.test")
            self.other = User.objects.create_user(email="registry-delete-other@example.test")
            reviewer = User.objects.create_user(email="registry-delete-reviewer@example.test", is_staff=True)
            self.control = Company.objects.create(
                owner=self.owner,
                name="No History Pty Ltd",
                acn="100000682",
                status=CompanyStatus.REVIEW,
            )
            self.company = Company.objects.create(
                owner=self.owner,
                name="Reviewed Pty Ltd",
                acn="100001492",
                status=CompanyStatus.SUBMITTED,
            )
            with patch(
                "companies.services.registry.lookup_company", return_value=matching_observation(self.company)
            ), patch("companies.services.company.send_push_notification"):
                self.company = transition_company(self.company, "start_review", actor=reviewer)
            self.check_id = self.company.registry_check_id

    def test_an_owner_can_delete_a_reviewed_company_without_shares_and_its_hidden_history(self):
        self.signed_in_as(self.owner)
        control = self.client.delete(f"/api/v1/companies/{self.control.pk}/")
        self.assertEqual(control.status_code, 204, control.content)
        with use_operator():
            self.assertFalse(Company.objects.filter(pk=self.control.pk).exists())
            self.assertTrue(CompanyRegistryCheck.objects.filter(pk=self.check_id).exists())
        self.assertFalse(CompanyRegistryCheck.objects.filter(pk=self.check_id).exists())

        self.signed_in_as(self.other)
        refused = self.client.delete(f"/api/v1/companies/{self.company.pk}/")
        self.assertEqual(refused.status_code, 404, refused.content)
        with use_operator():
            self.assertTrue(Company.objects.filter(pk=self.company.pk).exists())
            self.assertTrue(CompanyRegistryCheck.objects.filter(pk=self.check_id).exists())

        self.signed_in_as(self.owner)
        response = self.client.delete(f"/api/v1/companies/{self.company.pk}/")
        self.assertEqual(response.status_code, 204, response.content)
        with use_operator():
            self.assertFalse(Company.objects.filter(pk=self.company.pk).exists())
            self.assertFalse(CompanyRegistryCheck.objects.filter(pk=self.check_id).exists())

    def test_a_reviewed_company_with_a_share_class_still_refuses_deletion(self):
        with use_operator():
            token = ShareToken.objects.create(company=self.company, name="Ordinary", symbol="REG")
        self.signed_in_as(self.owner)

        response = self.client.delete(f"/api/v1/companies/{self.company.pk}/")

        self.assertEqual(response.status_code, 409, response.content)
        with use_operator():
            self.assertTrue(Company.objects.filter(pk=self.company.pk).exists())
            self.assertTrue(ShareToken.objects.filter(pk=token.pk).exists())
            self.assertTrue(CompanyRegistryCheck.objects.filter(pk=self.check_id).exists())
