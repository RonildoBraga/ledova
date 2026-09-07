from contextlib import contextmanager
from unittest import skipUnless

from django.conf import settings
from django.db import connection
from django.urls import resolve

from shared.tests.test_cross_tenant_routes import CrossTenantRouteMatrixTest

POSTGRES = connection.vendor == "postgresql"
REASON = (
    "the policies exist only in PostgreSQL, and on SQLite this class would run the matrix "
    "with nothing enforcing it and report the same green as the class it inherits from"
)


def runs_on_the_operator_connection(path, method):
    match = resolve(path.split("?", 1)[0])
    view = getattr(match.func, "cls", None) or getattr(match.func, "view_class", None)
    action = (getattr(match.func, "actions", None) or {}).get(method)
    return action in frozenset(getattr(view, "operator_actions", ()))


@skipUnless(POSTGRES, REASON)
class TheMatrixHoldsWhenTheDatabaseIsTheOnlyThingHoldingItTest(CrossTenantRouteMatrixTest):

    def setUp(self):
        super().setUp()
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            assumed = cursor.fetchone()[0]

        self.assertNotEqual(
            assumed,
            settings.RLS_ROLES["app"],
            "a previous test left the connection as the app role, so everything after it ran scoped by "
            "accident - the leak is the failure, not whatever fails next",
        )

    @contextmanager
    def as_the_app_role(self):
        with connection.cursor() as cursor:
            cursor.execute(f"SET ROLE {settings.RLS_ROLES['app']}")
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")

    def perform(self, route, context):
        path = route.path.format_map(context)
        if runs_on_the_operator_connection(path, route.method):
            return super().perform(route, context)
        with self.as_the_app_role():
            return super().perform(route, context)

    def test_the_split_is_a_split_and_not_one_side(self):
        somewhere = "00000000-0000-0000-0000-000000000000"

        self.assertTrue(runs_on_the_operator_connection(f"/api/v1/companies/{somewhere}/api-key/", "get"))
        self.assertFalse(runs_on_the_operator_connection(f"/api/v1/companies/{somewhere}/", "get"))
        self.assertFalse(runs_on_the_operator_connection("/api/wallets/", "get"))
