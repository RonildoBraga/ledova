from unittest import skipUnless

from django.apps import apps
from django.conf import settings
from django.db import connection
from django.test import TestCase

from shared.db.policies import POLICIES
from shared.db.principal import PRINCIPAL_SETTING
from shared.tests.tenants import make_tenant

POSTGRES = connection.vendor == "postgresql"
REASON = "the policies exist only in PostgreSQL, and without them every join is closed by definition"

ORPHANS = (
    "SELECT count(*) FROM {child} WHERE {column} IS NOT NULL "
    "AND NOT EXISTS (SELECT 1 FROM {parent} WHERE {parent}.{key} = {child}.{column})"
)


def nullable_links_between_policy_tables():
    links = []
    for model in apps.get_models():
        if model._meta.db_table not in POLICIES:
            continue
        for field in model._meta.concrete_fields:
            parent = getattr(field, "related_model", None)
            if parent is None or parent._meta.db_table not in POLICIES or not field.null:
                continue
            links.append((model._meta.db_table, field.column, parent._meta.db_table, parent._meta.pk.column))
    return sorted(set(links))


def links_between_policy_tables():
    links = []
    for model in apps.get_models():
        if model._meta.db_table not in POLICIES:
            continue
        for field in model._meta.concrete_fields:
            parent = getattr(field, "related_model", None)
            if parent is None or parent._meta.db_table not in POLICIES or field.null:
                continue
            links.append((model._meta.db_table, field.column, parent._meta.db_table, parent._meta.pk.column))
    return sorted(set(links))


@skipUnless(POSTGRES, REASON)
class AVisibleRowsParentIsVisibleTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.one = make_tenant("closureone")
        cls.two = make_tenant("closuretwo")

    def orphans(self, child, column, parent, key):
        with connection.cursor() as cursor:
            cursor.execute(ORPHANS.format(child=child, column=column, parent=parent, key=key))
            return cursor.fetchone()[0]

    def as_the_app_role_for(self, user):
        with connection.cursor() as cursor:
            cursor.execute(f"SET ROLE {settings.RLS_ROLES['app']}")
            cursor.execute("SELECT set_config(%s, %s, false)", [PRINCIPAL_SETTING, str(user.pk)])
        self.addCleanup(self.back_to_the_owner)

    def back_to_the_owner(self):
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(f"RESET {PRINCIPAL_SETTING}")

    def test_no_visible_row_points_at_a_parent_the_same_principal_cannot_see(self):
        for tenant in (self.one, self.two):
            self.as_the_app_role_for(tenant.user)
            for child, column, parent, key in links_between_policy_tables():
                with self.subTest(principal=tenant.user.pk, link=f"{child}.{column} -> {parent}"):
                    self.assertEqual(
                        self.orphans(child, column, parent, key),
                        0,
                        f"{child}.{column} survives its own policy while {parent} hides the row it points at, "
                        "so select_related turns the child into no row at all and count() disagrees with it",
                    )
            self.back_to_the_owner()

    def test_a_nullable_link_is_left_outer_and_keeps_its_row(self):
        for tenant in (self.one, self.two):
            self.as_the_app_role_for(tenant.user)
            for child, column, parent, key in nullable_links_between_policy_tables():
                with self.subTest(principal=tenant.user.pk, link=f"{child}.{column} -> {parent}"):
                    with connection.cursor() as cursor:
                        cursor.execute(
                            f"SELECT count(*) FROM {child} LEFT JOIN {parent} AS reached "
                            f"ON reached.{key} = {child}.{column}"
                        )
                        joined = cursor.fetchone()[0]
                        cursor.execute(f"SELECT count(*) FROM {child}")
                        alone = cursor.fetchone()[0]
                    self.assertEqual(joined, alone)
            self.back_to_the_owner()

    def test_the_graph_is_not_empty_so_the_assertion_discriminates(self):
        links = links_between_policy_tables()

        self.assertGreater(len(links), 5)
        self.assertIn(("offerings_subscription", "company_id", "companies_company", "uuid"), links)
