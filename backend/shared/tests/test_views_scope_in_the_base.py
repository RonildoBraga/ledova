from types import SimpleNamespace

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from shared.views.scope import ScopesToThePrincipal
from users.models import Notification, UserAccount


class Unscoped:
    pass


class ScopingRefusalsHappenAtImportTest(SimpleTestCase):

    def test_a_view_cannot_name_a_model_and_keep_its_own_get_queryset(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "put the product filtering in narrow()"):

            class Both(ScopesToThePrincipal):
                scoped_model = Notification

                def get_queryset(self):
                    return Notification.objects.all()

    def test_a_view_cannot_name_a_model_and_keep_its_own_get_object(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "get_object"):

            class Both(ScopesToThePrincipal):
                scoped_model = Notification

                def get_object(self):
                    return None

    def test_a_hook_without_a_model_is_refused(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "names no scoped_model"):

            class NoModel(ScopesToThePrincipal):
                def narrow(self, queryset):
                    return queryset

    def test_manage_actions_without_a_model_are_refused(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "names no scoped_model"):

            class NoModel(ScopesToThePrincipal):
                manage_actions = frozenset({"create"})

    def test_a_model_whose_manager_cannot_scope_is_refused(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "visible_to_user"):

            class Unscopable(ScopesToThePrincipal):
                scoped_model = SimpleNamespace(__name__="Unscopable", _default_manager=Unscoped())

    def test_manage_actions_need_a_manage_predicate(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "manageable_by_user"):

            class Manages(ScopesToThePrincipal):
                scoped_model = UserAccount
                manage_actions = frozenset({"create"})

    def test_a_view_that_names_no_model_and_no_hook_is_left_alone(self):
        class Untouched(ScopesToThePrincipal):
            pass

        self.assertIsNone(Untouched.scoped_model)


class RecordingManager:

    def __init__(self):
        self.calls = []

    def visible_to_user(self, user):
        self.calls.append("visible_to_user")
        return "the read scope"

    def manageable_by_user(self, user):
        self.calls.append("manageable_by_user")
        return "the manage scope"

    def all(self):
        self.calls.append("all")
        return "every row"


class TheBaseChoosesThePredicateTest(SimpleTestCase):

    def view(self, action, manage=frozenset(), administrative=frozenset()):
        manager = RecordingManager()

        class Scoped(ScopesToThePrincipal):
            scoped_model = SimpleNamespace(__name__="Recorded", _default_manager=manager)
            manage_actions = manage
            administrative_actions = administrative
            operator_actions = administrative

        scoped = Scoped()
        scoped.action = action
        scoped.request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, pk=1))
        return scoped, manager

    def test_a_read_action_takes_the_read_predicate_and_no_other(self):
        view, manager = self.view("list")

        self.assertEqual(view.get_queryset(), "the read scope")
        self.assertEqual(manager.calls, ["visible_to_user"])

    def test_a_manage_action_takes_the_manage_predicate_and_no_other(self):
        view, manager = self.view("update", manage=frozenset({"update"}))

        self.assertEqual(view.get_queryset(), "the manage scope")
        self.assertEqual(manager.calls, ["manageable_by_user"])

    def test_an_administrative_action_is_the_only_one_that_goes_unscoped(self):
        view, manager = self.view("verify", administrative=frozenset({"verify"}))

        self.assertEqual(view.get_queryset(), "every row")
        self.assertEqual(manager.calls, ["all"])

    def test_an_action_named_operator_but_not_administrative_is_refused_at_import(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "without naming them administrative"):

            class Wider(ScopesToThePrincipal):
                scoped_model = Notification
                operator_actions = frozenset({"a_market_read"})
                administrative_actions = frozenset()

    def test_narrow_receives_exactly_what_the_branch_produced(self):
        seen = []

        class Narrowing(ScopesToThePrincipal):
            scoped_model = SimpleNamespace(__name__="Recorded", _default_manager=RecordingManager())
            administrative_actions = frozenset({"sweep"})
            operator_actions = frozenset({"sweep"})

            def narrow(self, queryset):
                seen.append(queryset)
                return f"narrowed {queryset}"

        view = Narrowing()
        view.request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, pk=1))

        view.action = "list"
        self.assertEqual(view.get_queryset(), "narrowed the read scope")
        view.action = "sweep"
        self.assertEqual(view.get_queryset(), "narrowed every row")

        self.assertEqual(seen, ["the read scope", "every row"])
