from types import SimpleNamespace

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from shared.views.scope import ScopesToThePrincipal
from companies.models import Company
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


class TheBaseChoosesThePredicateTest(SimpleTestCase):

    def view(self, action, model=Company, manage=frozenset()):
        class Scoped(ScopesToThePrincipal):
            scoped_model = model
            manage_actions = manage
            operator_actions = frozenset()

        scoped = Scoped()
        scoped.action = action
        scoped.request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False, pk=None))
        return scoped

    def test_a_read_action_takes_the_read_predicate(self):
        self.assertEqual(self.view("list").get_queryset().model, Company)

    def test_a_manage_action_takes_the_manage_predicate(self):
        manage = frozenset({"update"})
        self.assertEqual(self.view("update", manage=manage).get_queryset().model, Company)

    def test_narrow_receives_the_already_scoped_queryset(self):
        seen = []

        class Narrowing(ScopesToThePrincipal):
            scoped_model = Notification
            operator_actions = frozenset()

            def narrow(self, queryset):
                seen.append(queryset.model)
                return queryset

        view = Narrowing()
        view.action = "list"
        view.request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False, pk=None))
        view.get_queryset()

        self.assertEqual(seen, [Notification])
