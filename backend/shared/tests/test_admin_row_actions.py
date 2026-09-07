import re
import uuid

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.http import Http404, HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from companies.models import Company, CompanyType
from shared.utils.admin_actions import admin_action_path

ACTION_HELPER = "shared.utils.admin_actions"
FILE_HELPER = "shared.utils.admin_files"
ACTION_GROUP = re.compile(r"\(\?P<action>([^)]+)\)")
ADMIN_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "private": {"BACKEND": "shared.storage.PrivateMediaStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

User = get_user_model()
PASSWORD = "pw-12345678"


def arguments_for(entry):
    actions = ACTION_GROUP.search(str(entry.pattern))
    if actions is None:
        return [uuid.uuid4()]
    return [uuid.uuid4(), actions.group(1).split("|")[0]]


def custom_routes():
    found = []
    for model_admin in admin.site._registry.values():
        default = {entry.name for entry in admin.ModelAdmin.get_urls(model_admin)}
        for entry in model_admin.get_urls():
            if entry.name in default or entry.callback.__module__.startswith("django."):
                continue
            found.append((entry, model_admin))
    return found


def row_action_routes():
    return [
        (entry.name, model_admin, arguments_for(entry))
        for entry, model_admin in custom_routes()
        if entry.callback.__module__ == ACTION_HELPER
    ]


def staff_user(label):
    return User.objects.create_user(
        email=f"{label}@example.test",
        password=PASSWORD,
        is_staff=True,
        is_active=True,
        is_email_verified=True,
    )


def grant(user, model_admin, action):
    content_type = ContentType.objects.get_for_model(model_admin.model, for_concrete_model=False)
    user.user_permissions.add(
        Permission.objects.get(content_type=content_type, codename=f"{action}_{model_admin.opts.model_name}")
    )
    return User.objects.get(pk=user.pk)


@override_settings(STORAGES=ADMIN_STORAGES)
class AdminRowActionRegistrationTest(TestCase):

    def test_every_custom_admin_route_is_served_by_a_shared_helper(self):
        stray = {
            entry.name: entry.callback.__module__
            for entry, _ in custom_routes()
            if entry.callback.__module__ not in (ACTION_HELPER, FILE_HELPER)
        }

        self.assertEqual(stray, {})

    def test_the_admin_registers_row_actions_at_all(self):
        self.assertNotEqual(row_action_routes(), [])


@override_settings(STORAGES=ADMIN_STORAGES)
class AdminRowActionAuthorizationTest(TestCase):

    def setUp(self):
        self.routes = row_action_routes()
        self.assertNotEqual(self.routes, [])

    def url(self, name, arguments):
        return reverse(f"admin:{name}", args=arguments)

    def test_staff_without_change_permission_are_refused_on_every_row_action(self):
        self.client.force_login(staff_user("row-action-plain"))
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)

        for name, _, arguments in self.routes:
            with self.subTest(route=name):
                self.assertEqual(self.client.get(self.url(name, arguments)).status_code, 403)

    def test_view_permission_alone_does_not_unlock_a_row_action(self):
        for index, (name, model_admin, arguments) in enumerate(self.routes):
            with self.subTest(route=name):
                user = grant(staff_user(f"row-action-viewer-{index}"), model_admin, "view")
                self.client.force_login(user)

                self.assertEqual(self.client.get(self.url(name, arguments)).status_code, 403)

    def test_change_permission_carries_the_caller_past_the_guard_and_no_further(self):
        for index, (name, model_admin, arguments) in enumerate(self.routes):
            with self.subTest(route=name):
                user = grant(staff_user(f"row-action-editor-{index}"), model_admin, "change")
                self.client.force_login(user)

                self.assertEqual(self.client.get(self.url(name, arguments)).status_code, 404)

    def test_a_superuser_reaches_every_row_action(self):
        self.client.force_login(User.objects.create_superuser(email="row-action-super@example.test", password=PASSWORD))

        for name, _, arguments in self.routes:
            with self.subTest(route=name):
                self.assertEqual(self.client.get(self.url(name, arguments)).status_code, 404)

    def test_an_anonymous_caller_is_redirected_to_the_admin_login(self):
        for name, _, arguments in self.routes:
            with self.subTest(route=name):
                response = self.client.get(self.url(name, arguments))

                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("admin:login"), response.headers["Location"])

    def test_the_guard_refuses_before_the_row_is_resolved(self):
        name, model_admin, arguments = self.routes[0]
        self.client.force_login(staff_user("row-action-ordering"))

        refused = self.client.get(self.url(name, arguments))
        self.client.force_login(grant(staff_user("row-action-ordering-editor"), model_admin, "change"))
        resolved = self.client.get(self.url(name, arguments))

        self.assertEqual(refused.status_code, 403)
        self.assertEqual(resolved.status_code, 404)


@override_settings(STORAGES=ADMIN_STORAGES)
class NarrowedRowsAreHonouredWhenEmptyTest(TestCase):

    def test_a_row_set_that_matches_nothing_does_not_fall_back_to_the_admins_own_queryset(self):
        owner = User.objects.create_user(email="rows-owner@example.test", password=PASSWORD)
        company = Company.objects.create(
            owner=owner, name="Narrowed Pty Ltd", company_type=CompanyType.PROPRIETARY, acn="444555666"
        )
        model_admin = admin.site._registry[Company]
        asked = []
        route = admin_action_path(
            model_admin,
            "<uuid:uuid>/narrowed-probe/",
            "narrowed_probe",
            lambda request, instance: HttpResponse(instance.name),
            rows=lambda request: asked.append(request) or Company.objects.none(),
        )
        request = RequestFactory().get("/")
        request.user = User.objects.create_superuser(email="rows-super@example.test", password=PASSWORD)

        with self.assertRaises(Http404):
            route.callback(request, uuid=company.uuid)

        self.assertEqual(len(asked), 1)

    def test_a_row_set_passed_as_a_queryset_rather_than_a_callable_fails_loudly(self):
        owner = User.objects.create_user(email="rows-loud-owner@example.test", password=PASSWORD)
        company = Company.objects.create(
            owner=owner, name="Loud Pty Ltd", company_type=CompanyType.PROPRIETARY, acn="777888999"
        )
        route = admin_action_path(
            admin.site._registry[Company],
            "<uuid:uuid>/loud-probe/",
            "loud_probe",
            lambda request, instance: HttpResponse(instance.name),
            rows=Company.objects.none(),
        )
        request = RequestFactory().get("/")
        request.user = User.objects.create_superuser(email="rows-loud-super@example.test", password=PASSWORD)

        with self.assertRaises(TypeError):
            route.callback(request, uuid=company.uuid)
