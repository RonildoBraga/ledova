import ast
import inspect
import textwrap

from django.db import models
from django.test import SimpleTestCase
from django.urls import get_resolver
from rest_framework.relations import ManyRelatedField, RelatedField

from shared.tests import test_cross_tenant_routes as matrix
from shared.tests import test_route_coverage as coverage
from shared.tests.test_route_coverage import EXEMPT

BACKEND = coverage.__file__.rsplit("/backend/", 1)[0] + "/backend"

OWNER_MODELS = ("CustomUser", "UserProfile", "UserAccount", "Company")

IDENTITY_FREE_USER_READS = frozenset({"is_authenticated"})

REASONS_WITH_A_TEST = {
    "UNAUTHENTICATED_AUTH",
    "PROVIDER_WEBHOOK",
    "GLOBAL_CATALOGUE",
    "CREATES_OWN_ROW",
    "CREATES_OWN_ROW_SCOPED_FK",
    "SELF_SCOPED",
    "ELIGIBILITY_SCOPED",
    "ELIGIBILITY_SCOPED_ASYNC",
    "SIGNED_RELAY",
    "STAFF_UNSCOPED",
    "STAFF_WHITELIST",
    "BODY_IDENTIFIED",
    "CHAIN_ADDRESS_READ",
}


def _callbacks():
    found = {}
    for raw, callback in coverage._walk(get_resolver().url_patterns):
        normalised = coverage._normalise(raw)
        view = getattr(callback, "cls", None)
        if getattr(view, "__name__", "") == "APIRootView":
            continue
        for method in coverage._methods(callback):
            found.setdefault((method, normalised), (callback, raw))
    return found


CALLBACKS = _callbacks()


def _reason_names():
    named = {}
    for name, value in vars(coverage).items():
        if isinstance(value, str) and name.isupper():
            named.setdefault(id(value), name)
    return named


REASON_NAME = _reason_names()


def routes_for(name):
    return sorted(route for route, reason in EXEMPT.items() if REASON_NAME.get(id(reason)) == name)


def view_for(route):
    callback, _ = CALLBACKS[route]
    return getattr(callback, "cls", None)


def permissions_for(route):
    callback, _ = CALLBACKS[route]
    view = getattr(callback, "cls", None)
    if view is None:
        return None
    instance = view(**getattr(callback, "initkwargs", {}))
    instance.action = (getattr(callback, "actions", None) or {}).get(route[0])
    instance.request = None
    instance.format_kwarg = None
    return sorted(type(permission).__name__ for permission in instance.get_permissions())


def model_for(route):
    callback, _ = CALLBACKS[route]
    view = getattr(callback, "cls", None)
    declared = getattr(view, "queryset", None)
    if declared is not None:
        return declared.model
    serializer = getattr(view, "serializer_class", None)
    return getattr(getattr(serializer, "Meta", None), "model", None)


def writable_relations(route):
    callback, _ = CALLBACKS[route]
    view = getattr(callback, "cls", None)
    instance = view(**getattr(callback, "initkwargs", {}))
    instance.action = (getattr(callback, "actions", None) or {}).get(route[0])
    instance.request = None
    instance.format_kwarg = None
    serializer = instance.get_serializer_class()()
    return {
        name: field
        for name, field in serializer.fields.items()
        if isinstance(field, (RelatedField, ManyRelatedField)) and not field.read_only
    }


class EveryReasonIsTestedTest(SimpleTestCase):

    def test_every_reason_in_use_has_a_test_in_this_module(self):
        in_use = {REASON_NAME.get(id(reason)) for reason in EXEMPT.values()}

        self.assertEqual(in_use - REASONS_WITH_A_TEST, set())

    def test_no_test_here_outlives_the_reason_it_checks(self):
        in_use = {REASON_NAME.get(id(reason)) for reason in EXEMPT.values()}

        self.assertEqual(REASONS_WITH_A_TEST - in_use, set())

    def test_every_exempt_route_resolves_to_a_registered_callback(self):
        missing = sorted(route for route in EXEMPT if route not in CALLBACKS)

        self.assertEqual(missing, [])


class NoSessionReasonsTest(SimpleTestCase):

    def test_the_auth_surface_admits_a_caller_with_no_session(self):
        for route in routes_for("UNAUTHENTICATED_AUTH"):
            with self.subTest(route=route):
                self.assertEqual(permissions_for(route), ["AllowAny"])

    def test_a_provider_webhook_carries_no_permission_that_wants_a_session(self):
        for route in routes_for("PROVIDER_WEBHOOK"):
            with self.subTest(route=route):
                self.assertEqual(permissions_for(route), [])


class StaffReasonsTest(SimpleTestCase):

    def test_the_unscoped_company_actions_are_staff_only(self):
        for route in routes_for("STAFF_UNSCOPED"):
            with self.subTest(route=route):
                self.assertIn("IsAdminUser", permissions_for(route))

    def test_whitelist_administration_is_staff_only(self):
        for route in routes_for("STAFF_WHITELIST"):
            with self.subTest(route=route):
                self.assertIn("IsAdminUser", permissions_for(route))


class TakesNoIdentifierReasonsTest(SimpleTestCase):

    def test_a_self_scoped_route_takes_no_path_identifier(self):
        for method, path in routes_for("SELF_SCOPED"):
            with self.subTest(route=(method, path)):
                self.assertNotIn("{}", path)

    def test_a_body_identified_route_takes_no_path_identifier(self):
        for method, path in routes_for("BODY_IDENTIFIED"):
            with self.subTest(route=(method, path)):
                self.assertNotIn("{}", path)

    def test_the_signed_relay_takes_no_path_identifier(self):
        for method, path in routes_for("SIGNED_RELAY"):
            with self.subTest(route=(method, path)):
                self.assertNotIn("{}", path)


class CreationReasonsTest(SimpleTestCase):

    def test_a_creation_route_that_claims_no_writable_relation_has_none(self):
        for route in routes_for("CREATES_OWN_ROW"):
            with self.subTest(route=route):
                self.assertEqual(sorted(writable_relations(route)), [])

    def test_a_scoped_creation_routes_relations_cannot_name_a_tenants_row(self):
        for route in routes_for("CREATES_OWN_ROW_SCOPED_FK"):
            for name, field in writable_relations(route).items():
                with self.subTest(route=route, field=name):
                    queryset = getattr(field, "queryset", None)
                    if queryset is None or queryset.query.is_empty():
                        continue
                    owners = [
                        related.name
                        for related in queryset.model._meta.get_fields()
                        if isinstance(related, models.ForeignKey) and related.related_model.__name__ in OWNER_MODELS
                    ]
                    self.assertEqual(owners, [])


class CataloguesAndListingsTest(SimpleTestCase):

    def test_a_global_catalogue_answers_the_same_rows_to_every_signed_in_caller(self):
        for route in routes_for("GLOBAL_CATALOGUE"):
            model = model_for(route)
            with self.subTest(route=route):
                self.assertIsNotNone(model)
                scoping = ast.parse(textwrap.dedent(inspect.getsource(model.objects.visible_to_user)))

                for node in ast.walk(scoping):
                    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                        if node.value.id == "user":
                            self.assertIn(node.attr, IDENTITY_FREE_USER_READS)
                    if isinstance(node, ast.Call):
                        for argument in node.args + [keyword.value for keyword in node.keywords]:
                            if isinstance(argument, ast.Name):
                                self.assertNotEqual(argument.id, "user")

    def test_the_eligibility_scoped_listings_are_pinned_by_the_matrix(self):
        self.assertNotEqual(matrix.MARKET_ROUTES, ())
        self.assertNotEqual(matrix.DIRECTORY_ROUTES, ())

    def test_the_async_stream_is_a_plain_django_view_the_matrix_cannot_authenticate(self):
        for route in routes_for("ELIGIBILITY_SCOPED_ASYNC"):
            with self.subTest(route=route):
                self.assertIsNone(view_for(route))


class ChainAddressReadTest(SimpleTestCase):

    def test_the_route_takes_an_address_rather_than_a_row_identifier(self):
        for route in routes_for("CHAIN_ADDRESS_READ"):
            _, raw = CALLBACKS[route]
            with self.subTest(route=route):
                self.assertIn("<str:address>", raw)
                self.assertNotIn("uuid", raw)
