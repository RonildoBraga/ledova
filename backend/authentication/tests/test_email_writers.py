from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from authentication.admin.user import CustomUserAdmin, CustomUserCreationForm
from authentication.email import EMAIL_ERROR, EmailError
from authentication.services.tokens import TokenService

User = get_user_model()

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


class EmailManagerWriterTests(TestCase):
    password = "writer-password-123"

    def create_direct_user(self, email):
        user = User(email=email)
        user.set_password(self.password)
        user.save()
        return user

    def test_manager_normalization_exposes_the_v2_contract(self):
        self.assertEqual(
            User.objects.normalize_email(" Owner.Name+Tag@EXAMPLE.TEST "),
            "owner.name+tag@example.test",
        )
        with self.assertRaises(EmailError) as raised:
            User.objects.normalize_email("owner@example.test\t")
        self.assertEqual(str(raised.exception), EMAIL_ERROR)

    def test_user_and_superuser_creation_store_the_destination_key(self):
        user = User.objects.create_user(
            email=" Owner.Name+Tag@EXAMPLE.TEST ",
            password=self.password,
        )
        superuser = User.objects.create_superuser(
            email=" Admin.Name@EXAMPLE.TEST ",
            password=self.password,
        )

        self.assertEqual(user.email, "owner.name+tag@example.test")
        self.assertTrue(user.check_password(self.password))
        self.assertEqual(superuser.email, "admin.name@example.test")
        self.assertTrue(superuser.is_staff)
        self.assertTrue(superuser.is_superuser)

    def test_invalid_values_fail_with_a_fixed_error_and_no_row(self):
        invalid_values = (
            "owner@example.test\t",
            "owner@example.test\u00a0",
            "ownér@example.test",
            "not-an-email",
            f"{'a' * 242}@example.test",
            123,
        )

        for value in invalid_values:
            with self.subTest(value=repr(value)), self.assertRaises(EmailError) as raised:
                User.objects.create_user(email=value, password=self.password)
            self.assertEqual(str(raised.exception), EMAIL_ERROR)
            self.assertNotIn(str(value), str(raised.exception))
        self.assertFalse(User.objects.exists())

    def test_existing_destination_key_blocks_user_and_superuser_creation(self):
        self.create_direct_user("legacy.owner@example.test")

        with self.assertRaisesRegex(ValueError, r"^Email is unavailable\.$"):
            User.objects.create_user(
                email=" Legacy.Owner@EXAMPLE.TEST ",
                password=self.password,
            )

        with self.assertRaisesRegex(ValueError, r"^Email is unavailable\.$"):
            User.objects.create_superuser(
                email="LEGACY.OWNER@EXAMPLE.TEST",
                password=self.password,
            )

        self.assertEqual(User.objects.count(), 1)


class EmailAdminWriterTests(TestCase):
    password = "writer-password-123"

    def form(self, email):
        return CustomUserCreationForm(
            data={
                "email": email,
                "password1": self.password,
                "password2": self.password,
            }
        )

    def test_add_form_preserves_raw_input_until_v2_normalization(self):
        form = self.form(" Admin.Owner@EXAMPLE.TEST ")

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        self.assertEqual(user.email, "admin.owner@example.test")
        self.assertTrue(user.check_password(self.password))

    def test_add_form_rejects_disallowed_and_unavailable_values(self):
        invalid = self.form("admin.owner@example.test\t")
        self.assertFalse(invalid.is_valid())
        self.assertEqual(invalid.errors["email"], ["Enter a valid email address."])

        existing = User(email="legacy.admin@example.test")
        existing.set_password(self.password)
        existing.save()
        collision = self.form(" Legacy.Admin@EXAMPLE.TEST ")
        self.assertFalse(collision.is_valid())
        self.assertEqual(collision.errors["email"], ["Email is unavailable."])
        self.assertEqual(User.objects.count(), 1)


@override_settings(STORAGES=TEST_STORAGES)
class EmailAdminChangeTests(TestCase):
    """Staff can correct an address; the change form applies the same canonical validation as the API
    (never the DB constraint as a 500) and a changed address ends every session."""

    password = "writer-password-123"

    def setUp(self):
        super().setUp()
        self.superuser = User.objects.create_superuser(email="admin@example.test", password=self.password)
        self.target = User.objects.create_user(
            email="member@example.test", password=self.password, is_email_verified=True
        )
        self.other = User.objects.create_user(email="legacy.owner@example.test", password=self.password)
        self.change_url = reverse("admin:authentication_customuser_change", args=[self.target.pk])
        self.client.force_login(self.superuser)

    @staticmethod
    def change_data(email):
        return {
            "email": email,
            "date_joined_0": "2026-01-01",
            "date_joined_1": "00:00:00",
            "is_active": "on",
            "is_email_verified": "on",
        }

    def issue_sessions(self):
        return [TokenService.issue(self.target)[1] for _ in range(2)]

    def assert_sessions_live(self, refresh_tokens, live):
        from rest_framework_simplejwt.tokens import RefreshToken

        for raw in refresh_tokens:
            self.assertIs(TokenService.is_session_live(RefreshToken(raw, verify=False)["jti"]), live)

    def test_email_is_editable_on_the_change_form(self):
        request = RequestFactory().get("/")
        request.user = self.superuser
        model_admin = CustomUserAdmin(User, admin.site)

        self.assertNotIn("email", model_admin.get_readonly_fields(request, self.target))
        self.assertIn("email", model_admin.get_form(request, self.target).base_fields)

    def test_change_normalises_the_address_revokes_every_session_and_unverifies_it(self):
        sessions = self.issue_sessions()

        response = self.client.post(self.change_url, self.change_data(" Member.Renamed@EXAMPLE.TEST "))

        self.assertEqual(response.status_code, 302)
        self.target.refresh_from_db()
        self.assertEqual(self.target.email, "member.renamed@example.test")
        self.assertFalse(self.target.is_email_verified)
        self.assert_sessions_live(sessions, False)

    def test_same_address_in_another_spelling_changes_nothing_and_keeps_sessions(self):
        sessions = self.issue_sessions()

        response = self.client.post(self.change_url, self.change_data(" Member@EXAMPLE.TEST "))

        self.assertEqual(response.status_code, 302)
        self.target.refresh_from_db()
        self.assertEqual(self.target.email, "member@example.test")
        self.assertTrue(self.target.is_email_verified)
        self.assert_sessions_live(sessions, True)

    def test_colliding_and_invalid_addresses_are_form_errors_not_constraint_failures(self):
        sessions = self.issue_sessions()
        cases = (
            (" Legacy.Owner@EXAMPLE.TEST ", ["Email is unavailable."]),
            ("member@example.test\t", ["Enter a valid email address."]),
            ("not-an-email", ["Enter a valid email address."]),
        )

        for email, errors in cases:
            with self.subTest(email=repr(email)):
                response = self.client.post(self.change_url, self.change_data(email))

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["adminform"].form.errors["email"], errors)
        self.target.refresh_from_db()
        self.assertEqual(self.target.email, "member@example.test")
        self.assertEqual(User.objects.count(), 3)
        self.assert_sessions_live(sessions, True)
