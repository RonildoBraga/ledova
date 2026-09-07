from unittest import skipUnless

from django.conf import settings
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from shared.db import (
    APP_ALIAS,
    MIGRATE_ALIAS,
    OPERATOR_ALIAS,
    clear_alias,
    current_alias,
    use_operator,
)
from shared.db.middleware import view_runs_on_the_operator_connection
from shared.db.principal import PRINCIPAL_SETTING, principal_of
from shared.db.router import LedovaRouter
from shared.tests.tenants import make_tenant
from shared.views.principal import SetsThePrincipalOnTheConnection
from wallets.models import Wallet

POSTGRES = connection.vendor == "postgresql"
REASON = "the principal is a PostgreSQL setting, and set_config does not exist anywhere else"
THREE_ALIASES = {APP_ALIAS, OPERATOR_ALIAS, MIGRATE_ALIAS} <= set(settings.DATABASES)
ALIAS_REASON = "the three aliases are configured only where requests are served on a separate connection"


class Marked:
    runs_on_the_operator_connection = True


class Plain:
    pass


class TheRouterAsksTheThreadAndNothingElseTest(SimpleTestCase):

    def setUp(self):
        self.addCleanup(clear_alias)
        self.router = LedovaRouter()

    @skipUnless(THREE_ALIASES, ALIAS_REASON)
    @override_settings(RLS_AMBIENT_ALIAS=APP_ALIAS)
    def test_an_unselected_thread_reads_and_writes_on_the_scoped_alias(self):
        clear_alias()

        self.assertEqual(self.router.db_for_read(Wallet), APP_ALIAS)
        self.assertEqual(self.router.db_for_write(Wallet), APP_ALIAS)

    @skipUnless(THREE_ALIASES, ALIAS_REASON)
    @override_settings(RLS_AMBIENT_ALIAS=APP_ALIAS)
    def test_an_operator_context_selects_the_operator_alias_and_gives_it_back(self):
        with use_operator():
            self.assertEqual(self.router.db_for_read(Wallet), OPERATOR_ALIAS)

        self.assertEqual(self.router.db_for_read(Wallet), APP_ALIAS)

    def test_only_the_migrate_alias_may_run_migrations(self):
        self.assertTrue(self.router.allow_migrate(MIGRATE_ALIAS, "wallets"))
        self.assertFalse(self.router.allow_migrate(APP_ALIAS, "wallets"))
        self.assertFalse(self.router.allow_migrate(OPERATOR_ALIAS, "wallets"))

    def test_a_process_that_sets_nothing_serves_on_the_scoped_alias(self):
        source = (settings.BASE_DIR / "ledova_backend" / "settings" / "database.py").read_text()

        self.assertIn('RLS_AMBIENT_ALIAS = os.environ.get("RLS_AMBIENT_ALIAS", "app")', source)

    def test_the_current_alias_follows_the_setting_when_nothing_is_selected(self):
        clear_alias()

        self.assertEqual(current_alias(), settings.RLS_AMBIENT_ALIAS)


class TheOperatorConnectionIsChosenByWhatTheCodeSaysTest(SimpleTestCase):

    def test_a_marked_view_runs_on_the_operator_connection(self):
        self.assertTrue(view_runs_on_the_operator_connection(Marked, None))

    def test_an_unmarked_view_does_not(self):
        self.assertFalse(view_runs_on_the_operator_connection(Plain, None))

    def test_the_admin_is_recognised_by_its_urlconf_rather_than_by_its_path(self):
        resolved = type("Match", (), {"app_name": "admin"})()

        self.assertTrue(view_runs_on_the_operator_connection(Plain, resolved))

    def test_a_path_that_merely_looks_like_the_admin_is_not_enough(self):
        resolved = type("Match", (), {"app_name": "companies"})()

        self.assertFalse(view_runs_on_the_operator_connection(Plain, resolved))


@skipUnless(POSTGRES, REASON)
class TheRequestNamesItsPrincipalExactlyOnceTest(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.tenant = make_tenant("principal")

    @staticmethod
    def _named(captured):
        touching = [entry["sql"] for entry in captured.captured_queries if PRINCIPAL_SETTING in entry["sql"]]
        return (
            [sql for sql in touching if "NULL" not in sql],
            [sql for sql in touching if "NULL" in sql],
        )

    def test_an_authenticated_request_sets_the_principal_once(self):
        self.client.force_authenticate(self.tenant.user)

        with CaptureQueriesContext(connection) as captured:
            self.client.get("/api/wallets/")

        setting, _ = self._named(captured)
        self.assertEqual(len(setting), 1)
        self.assertIn(str(self.tenant.user.pk), setting[0])

    def test_an_unauthenticated_request_names_no_principal(self):
        with CaptureQueriesContext(connection) as captured:
            self.client.get("/api/wallets/")

        setting, _ = self._named(captured)
        self.assertEqual(setting, [])

    def test_every_request_clears_the_principal_on_the_way_out(self):
        self.client.force_authenticate(self.tenant.user)

        with CaptureQueriesContext(connection) as captured:
            self.client.get("/api/wallets/")

        _, cleared = self._named(captured)
        self.assertEqual(len(cleared), 1)

    def test_the_principal_does_not_survive_the_response(self):
        self.client.force_authenticate(self.tenant.user)

        self.client.get("/api/wallets/")

        self.assertIn(principal_of(), (None, ""))


@skipUnless(POSTGRES, REASON)
class TheMixinIsWhatSetsItTest(TestCase):

    def test_every_shared_view_base_carries_the_mixin(self):
        from shared.views.base import (
            AuthenticatedGenericViewSet,
            AuthenticatedListViewSet,
            AuthenticatedModelViewSet,
            AuthenticatedReadOnlyViewSet,
        )

        for base in (
            AuthenticatedGenericViewSet,
            AuthenticatedListViewSet,
            AuthenticatedModelViewSet,
            AuthenticatedReadOnlyViewSet,
        ):
            with self.subTest(base=base.__name__):
                self.assertTrue(issubclass(base, SetsThePrincipalOnTheConnection))


class TheProcessDecidesWhichConnectionItServesOnTest(SimpleTestCase):

    def test_only_the_request_serving_process_defaults_to_the_scoped_alias(self):
        source = (settings.BASE_DIR / "manage.py").read_text()

        self.assertIn('SERVES_REQUESTS = ("runserver",)', source)
        self.assertIn('os.environ.setdefault("RLS_AMBIENT_ALIAS", "operator")', source)

    def test_the_worker_runs_its_tasks_on_the_operator_connection(self):
        source = (settings.BASE_DIR / "ledova_backend" / "worker_entrypoint.py").read_text()

        self.assertIn('"RLS_AMBIENT_ALIAS": "operator"', source)

    @override_settings(RLS_AMBIENT_ALIAS=MIGRATE_ALIAS)
    def test_one_connection_deployments_collapse_every_alias_onto_it(self):
        from shared.db.aliases import configured

        self.assertEqual(configured(APP_ALIAS), MIGRATE_ALIAS)
        self.assertEqual(configured(OPERATOR_ALIAS), MIGRATE_ALIAS)
