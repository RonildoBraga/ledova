from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from authentication.admin.user import CustomUserAdmin, V2UserCreationForm
from authentication.security.v2_email import V2_EMAIL_ERROR, V2EmailError

User = get_user_model()


class V2EmailManagerWriterTests(TestCase):
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
        with self.assertRaises(V2EmailError) as raised:
            User.objects.normalize_email("owner@example.test\t")
        self.assertEqual(str(raised.exception), V2_EMAIL_ERROR)

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
            with self.subTest(value=repr(value)), self.assertRaises(V2EmailError) as raised:
                User.objects.create_user(email=value, password=self.password)
            self.assertEqual(str(raised.exception), V2_EMAIL_ERROR)
            self.assertNotIn(str(value), str(raised.exception))
        self.assertFalse(User.objects.exists())

    def test_existing_destination_key_blocks_user_and_superuser_creation(self):
        self.create_direct_user("legacy.owner@example.test")

        with self.assertRaisesRegex(ValueError, r"^V2 email is unavailable\.$"):
            User.objects.create_user(
                email=" Legacy.Owner@EXAMPLE.TEST ",
                password=self.password,
            )

        with self.assertRaisesRegex(ValueError, r"^V2 email is unavailable\.$"):
            User.objects.create_superuser(
                email="LEGACY.OWNER@EXAMPLE.TEST",
                password=self.password,
            )

        self.assertEqual(User.objects.count(), 1)


class V2EmailAdminWriterTests(TestCase):
    password = "writer-password-123"

    def form(self, email):
        return V2UserCreationForm(
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

    def test_existing_user_email_is_absent_from_the_change_form(self):
        superuser = User.objects.create_superuser(
            email="admin@example.test",
            password=self.password,
        )
        target = User.objects.create_user(
            email="member@example.test",
            password=self.password,
        )
        request = RequestFactory().get("/")
        request.user = superuser
        model_admin = CustomUserAdmin(User, admin.site)

        self.assertIn("email", model_admin.get_readonly_fields(request, target))
        form_class = model_admin.get_form(request, target)
        self.assertNotIn("email", form_class.base_fields)
