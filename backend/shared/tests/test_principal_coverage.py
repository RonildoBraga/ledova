from django.test import SimpleTestCase
from django.urls import get_resolver
from django.urls.resolvers import URLPattern, URLResolver

from shared.db.middleware import OPERATOR_MARKER
from shared.views.principal import PRINCIPAL_MARKER

NO_PRINCIPAL_NEEDED = {
    "rest_framework.routers.APIRootView": (
        "The router's own index. It lists the routes it registered and reads no table, so there is "
        "nothing for a policy to scope and nothing for a principal to name."
    ),
    "django.views.static.serve": (
        "Serves MEDIA_ROOT from disk. It touches no model, and the route exists only while DEBUG is on, "
        "because in production the files are served by the front door rather than by Django."
    ),
    "django.contrib.auth.views.LoginView": (
        "The browsable API's session login at /api-auth/, which reads auth_user and the session table. "
        "Both are outside the policy set, and the caller has no principal until it succeeds."
    ),
    "django.contrib.auth.views.LogoutView": (
        "The browsable API's session logout at /api-auth/. It deletes a session row and reads no "
        "tenant table, and by the time it matters the principal is being discarded anyway."
    ),
}


ROUTED_ONLY_IN_DEBUG = {"django.views.static.serve"}

STAFF_PERMISSIONS = frozenset({"IsAdminUser"})

STAFF_ACTIONS_ON_THE_SCOPED_CONNECTION = {
    "whitelist.views.entry.WhitelistEntryViewSet": (
        "Staff-only for every action through IsAdminUser at class level, and it stays on the scoped "
        "connection because the table it reads carries no policy: the whitelist is an authorisation surface "
        "rather than a tenancy one, and WhitelistEntry.visible_to_user returns self for staff. Putting it on "
        "the operator connection would hand BYPASSRLS to a staff API surface that does not need it. The day "
        "the table gains a policy this must move, and the test below is what says so.",
        ("whitelist_whitelistentry",),
    ),
}


def staff_only_everywhere(target):
    named = {klass.__name__ for klass in getattr(target, "permission_classes", None) or ()}
    return bool(named & STAFF_PERMISSIONS)


def walk(patterns, prefix="", app=None):
    for entry in patterns:
        raw = str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from walk(entry.url_patterns, prefix + raw, entry.app_name or app)
        elif isinstance(entry, URLPattern):
            yield prefix + raw, entry.callback, app


def target_of(callback):
    return getattr(callback, "cls", None) or getattr(callback, "view_class", None) or callback


def name_of(callback):
    target = target_of(callback)
    return f"{target.__module__}.{target.__qualname__}"


def routed_views():
    views = {}
    for path, callback, app in walk(get_resolver().url_patterns):
        views.setdefault(name_of(callback), (target_of(callback), app, set()))[2].add("/" + path.lstrip("/"))
    return views


class EveryRoutedViewSaysWhichConnectionItRunsOnTest(SimpleTestCase):

    def test_a_routed_view_sets_the_principal_runs_as_operator_or_is_exempt_with_a_reason(self):
        unclassified = []
        for name, (target, app, paths) in sorted(routed_views().items()):
            if getattr(target, PRINCIPAL_MARKER, False):
                continue
            if app == "admin" or getattr(target, OPERATOR_MARKER, False):
                continue
            if name in NO_PRINCIPAL_NEEDED:
                continue
            unclassified.append(f"{name} ({sorted(paths)[0]})")

        self.assertEqual(
            unclassified,
            [],
            "Each of these serves a request on the scoped connection without naming a principal. "
            "Inherit a shared base or SetsThePrincipalOnTheConnection, mark it "
            "RunsOnTheOperatorConnection, or add it to NO_PRINCIPAL_NEEDED with the reason.",
        )

    def test_no_exemption_outlives_the_route_it_excuses(self):
        routed = set(routed_views())

        self.assertEqual(sorted(set(NO_PRINCIPAL_NEEDED) - routed - ROUTED_ONLY_IN_DEBUG), [])

    def test_every_exemption_states_a_reason_rather_than_a_label(self):
        for name, reason in NO_PRINCIPAL_NEEDED.items():
            with self.subTest(view=name):
                self.assertGreater(len(reason), 80, f"{name} needs a reason, not a label")

    def test_the_check_would_notice_a_view_that_names_no_principal(self):
        classified = [
            name
            for name, (target, app, _) in routed_views().items()
            if getattr(target, PRINCIPAL_MARKER, False) or app == "admin" or getattr(target, OPERATOR_MARKER, False)
        ]

        self.assertGreater(len(classified), 30)


class AStaffOnlyActionSaysWhichConnectionItRunsOnTest(SimpleTestCase):

    def test_every_administrative_action_runs_on_the_operator_connection(self):
        borrowing = []
        for name, (target, _, _) in sorted(routed_views().items()):
            if name in STAFF_ACTIONS_ON_THE_SCOPED_CONNECTION:
                continue
            operator = frozenset(getattr(target, "operator_actions", ()))
            if staff_only_everywhere(target) and not operator:
                borrowing.append(f"{name}: staff-only for every action")
                continue
            unrouted = frozenset(getattr(target, "administrative_actions", ())) - operator
            if unrouted:
                borrowing.append(f"{name}: {sorted(unrouted)}")

        self.assertEqual(
            borrowing,
            [],
            "A staff-only action reaches every tenant, and a staff member does not own the rows it reaches, "
            "so the scoped connection hides them. Name the actions in operator_actions, or add the view to "
            "STAFF_ACTIONS_ON_THE_SCOPED_CONNECTION with the reason its staff actions stay scoped.",
        )

    def test_the_check_would_notice_an_action_that_borrowed_the_scoped_connection(self):
        found = [
            name
            for name, (target, _, _) in routed_views().items()
            if frozenset(getattr(target, "administrative_actions", ()))
        ]

        self.assertNotEqual(found, [])

    def test_every_exemption_states_a_reason_rather_than_a_label(self):
        for name, (reason, _) in STAFF_ACTIONS_ON_THE_SCOPED_CONNECTION.items():
            with self.subTest(view=name):
                self.assertGreater(len(reason), 60, f"{name} needs a reason, not a label")

    def test_every_exemption_rests_on_a_table_that_really_carries_no_policy(self):
        from shared.db.policies import POLICIES

        for name, (_, unpoliced) in STAFF_ACTIONS_ON_THE_SCOPED_CONNECTION.items():
            with self.subTest(view=name):
                self.assertNotEqual(unpoliced, ())
                self.assertEqual(sorted(set(unpoliced) & set(POLICIES)), [])

    def test_the_only_staff_implying_permission_classes_are_the_known_ones(self):
        seen = set()
        for _, (target, _, _) in routed_views().items():
            seen |= {klass.__name__ for klass in getattr(target, "permission_classes", None) or ()}

        self.assertEqual(sorted(seen - {"IsAuthenticated"} - STAFF_PERMISSIONS), [])
