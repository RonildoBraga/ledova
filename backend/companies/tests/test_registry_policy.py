from contextlib import contextmanager
from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import ProgrammingError, connections
from django.test import TestCase

from companies.identity import company_identity
from companies.models import (
    Company,
    CompanyRegistryCheck,
    CompanyStatus,
    RegistryCheckPurpose,
)
from shared.db import atomic, current_alias
from shared.db.principal import PRINCIPAL_SETTING


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

    def test_history_is_hidden_from_owners_investors_and_missing_principals(self):
        self.assertEqual(list(CompanyRegistryCheck.objects.all()), [self.check])
        for user in (self.owner, self.other, None):
            with self.subTest(user=user), self.as_app(user):
                self.assertTrue(Company.objects.filter(pk=self.company.pk).exists())
                self.assertFalse(CompanyRegistryCheck.objects.exists())
                self.assertFalse(CompanyRegistryCheck.objects.select_for_update().exists())
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
