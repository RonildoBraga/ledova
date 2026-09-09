import ast
import sys
from contextlib import contextmanager
from unittest import TestSuite, defaultTestLoader, skipUnless

from django.conf import settings
from django.db import connection, transaction
from django.test import SimpleTestCase
from django.urls import resolve

from shared.db import (
    APP_ALIAS,
    MIGRATE_ALIAS,
    OPERATOR_ALIAS,
    atomic,
    current_alias,
    set_principal,
    use_operator,
)
from shared.tests import test_cross_tenant_routes as matrix
from shared.tests.scoped import RunsOnTheScopedConnection

ROUTES = matrix.ROUTES

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


SINGLE_CONNECTION = settings.RLS_AMBIENT_ALIAS == MIGRATE_ALIAS
NOT_SINGLE_CONNECTION = (
    "this class takes the app role with SET ROLE on one connection, which is the only shape available "
    "where the ambient alias is the migrate one; under a scoped alias the class below is the "
    "authoritative run and this one would report the same green without the routing"
)


@skipUnless(POSTGRES, REASON)
@skipUnless(SINGLE_CONNECTION, NOT_SINGLE_CONNECTION)
class TheMatrixHoldsWhenTheDatabaseIsTheOnlyThingHoldingItTest(matrix.CrossTenantRouteMatrixTest):

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


class TheMatrixRunsOnTheConnectionTheRouterChoosesTest(RunsOnTheScopedConnection, matrix.CrossTenantRouteMatrixTest):

    def setUp(self):
        with self.as_an_operator_would():
            super().setUp()

    @contextmanager
    def undone_before_the_next_case(self):
        with atomic(), transaction.atomic(using=OPERATOR_ALIAS):
            yield
            transaction.set_rollback(True, using=current_alias())
            transaction.set_rollback(True, using=OPERATOR_ALIAS)

    @contextmanager
    def as_whoever_may_write_the_fixture(self, route, context, owner, actor):
        if runs_on_the_operator_connection(route.path.format_map(context), route.method):
            with use_operator():
                yield
            return
        set_principal(owner.user.pk, current_alias())
        try:
            yield
        finally:
            set_principal(actor.user.pk, current_alias())

    def test_the_requests_really_reach_the_scoped_connection(self):
        self.assertEqual(settings.RLS_AMBIENT_ALIAS, APP_ALIAS)
        self.assertEqual(current_alias(), APP_ALIAS)

    def test_it_runs_the_same_route_table_as_the_single_connection_class(self):
        self.assertEqual(
            sorted(f"{route.method} {route.path}" for route in ROUTES),
            sorted(f"{route.method} {route.path}" for route in matrix.CrossTenantRouteMatrixTest.routes()),
        )


def locking_request_views():
    names = set()
    for path in settings.BASE_DIR.glob("*/views/*.py"):
        module = ".".join(path.relative_to(settings.BASE_DIR).with_suffix("").parts)
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, ast.ClassDef) and any(
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "select_for_update"
                for call in ast.walk(node)
            ):
                names.add(f"{module}.{node.name}")
    return names


def every_case(suite):
    for item in suite:
        if isinstance(item, TestSuite):
            yield from every_case(item)
        else:
            yield item


class OnlyTheClassesDefinedHereAreCollectedTest(SimpleTestCase):

    def test_the_base_matrix_is_reached_through_its_module_and_never_bound_to_a_name(self):
        suite = defaultTestLoader.loadTestsFromModule(sys.modules[__name__])

        self.assertEqual(
            {type(case).__name__ for case in every_case(suite)},
            {
                "TheMatrixHoldsWhenTheDatabaseIsTheOnlyThingHoldingItTest",
                "TheMatrixRunsOnTheConnectionTheRouterChoosesTest",
                "OnlyTheClassesDefinedHereAreCollectedTest",
            },
            "unittest collects every TestCase subclass in dir(module) whatever it is called, so a "
            "name bound to the base runs the single-connection matrix a second time, under settings "
            "where it is not the authoritative run and carries no principal",
        )
