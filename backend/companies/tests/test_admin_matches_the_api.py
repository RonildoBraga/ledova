from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from rest_framework.exceptions import ValidationError

from companies.models import Company, CompanyStatus, CompanyType
from companies.serializers.company import CompanyUpdateSerializer

User = get_user_model()
PASSWORD = "pw-12345678"
ADMIN_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "private": {"BACKEND": "shared.storage.PrivateMediaStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def a_different_value(company, name):
    field = Company._meta.get_field(name)
    current = getattr(company, name)
    if field.choices:
        return next(value for value, _ in field.choices if value != current)
    if not isinstance(current, str):
        return None
    if current.isdigit():
        return "".join("9" if digit != "9" else "8" for digit in current)
    return f"{current}-changed"


class TheAdminIsNotMorePermissiveThanTheApiTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(email="company-admin@example.test", password=PASSWORD)
        self.owner = User.objects.create_user(email="company-owner@example.test", password=PASSWORD)
        self.company = Company.objects.create(
            owner=self.owner,
            name="Immutable Pty Ltd",
            company_type=CompanyType.PROPRIETARY,
            acn="123456789",
            abn="12123456789",
            status=CompanyStatus.ACTIVE,
        )
        self.model_admin = admin.site._registry[Company]

    def admin_editable(self, company):
        request = RequestFactory().get("/")
        request.user = self.superuser
        return set(self.model_admin.get_form(request, obj=company)().fields)

    def refused_at(self, company, status):
        standing = company.status
        company.status = status
        try:
            refused = set()
            for name in CompanyUpdateSerializer(instance=company).fields:
                replacement = a_different_value(company, name) if hasattr(company, name) else None
                if replacement is None:
                    continue
                serializer = CompanyUpdateSerializer(instance=company, data={name: replacement}, partial=True)
                try:
                    serializer.is_valid(raise_exception=True)
                except ValidationError as error:
                    if name in error.detail:
                        refused.add(name)
            return refused
        finally:
            company.status = standing

    def immutable_after_draft(self, company):
        return self.refused_at(company, CompanyStatus.ACTIVE) - self.refused_at(company, CompanyStatus.DRAFT)

    def test_the_probe_finds_the_fields_the_api_locks_and_nothing_else(self):
        self.assertEqual(self.immutable_after_draft(self.company), {"company_type", "acn", "abn"})

    def test_the_probe_does_not_mistake_an_invalid_value_for_an_immutable_field(self):
        self.company.abn = ""

        self.assertIn("abn", self.refused_at(self.company, CompanyStatus.DRAFT))
        self.assertNotIn("abn", self.immutable_after_draft(self.company))

    def test_no_field_the_api_refuses_to_change_is_editable_in_the_admin(self):
        immutable = self.immutable_after_draft(self.company)
        self.assertNotEqual(immutable, set())

        self.assertEqual(immutable & self.admin_editable(self.company), set())

    def test_a_draft_company_keeps_the_fields_the_api_still_allows(self):
        draft = Company.objects.create(
            owner=self.owner,
            name="Draft Pty Ltd",
            company_type=CompanyType.PROPRIETARY,
            acn="987654321",
            abn="98987654321",
            status=CompanyStatus.DRAFT,
        )

        self.assertLessEqual(self.immutable_after_draft(draft), self.admin_editable(draft))

    def test_the_owner_is_never_editable_on_an_existing_company(self):
        self.assertNotIn("owner", self.admin_editable(self.company))
        self.assertNotIn(
            "owner",
            self.admin_editable(
                Company.objects.create(
                    owner=self.owner,
                    name="Draft Owner Pty Ltd",
                    company_type=CompanyType.PROPRIETARY,
                    acn="555666777",
                    status=CompanyStatus.DRAFT,
                )
            ),
        )

    def test_the_add_form_still_asks_for_an_owner(self):
        request = RequestFactory().get("/")
        request.user = self.superuser

        self.assertIn("owner", set(self.model_admin.get_form(request, obj=None)().fields))


@override_settings(STORAGES=ADMIN_STORAGES)
class TheChangePageRefusesTheLockedFieldsTest(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user(email="post-owner@example.test", password=PASSWORD)
        self.other = User.objects.create_user(email="post-other@example.test", password=PASSWORD)
        self.company = Company.objects.create(
            owner=self.owner,
            name="Posted Pty Ltd",
            company_type=CompanyType.PROPRIETARY,
            acn="123456789",
            abn="12123456789",
            status=CompanyStatus.ACTIVE,
        )
        self.client.force_login(User.objects.create_superuser(email="post-admin@example.test", password=PASSWORD))

    def change_post(self, **changes):
        url = reverse("admin:companies_company_change", args=[self.company.pk])
        page = self.client.get(url)
        payload = {name: field.initial or "" for name, field in page.context["adminform"].form.fields.items()}
        for prefix in [inline.formset.prefix for inline in page.context["inline_admin_formsets"]]:
            payload.update(
                {
                    f"{prefix}-TOTAL_FORMS": "0",
                    f"{prefix}-INITIAL_FORMS": "0",
                    f"{prefix}-MIN_NUM_FORMS": "0",
                    f"{prefix}-MAX_NUM_FORMS": "1000",
                }
            )
        payload.update({"name": self.company.name, "status": self.company.status, **changes})
        return self.client.post(url, payload)

    def test_a_change_post_carrying_a_new_owner_and_acn_saves_but_moves_neither(self):
        response = self.change_post(
            owner=self.other.pk,
            acn="999888777",
            abn="99998888777",
            company_type=CompanyType.PUBLIC,
            trading_name="Renamed Trading",
        )
        self.company.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.company.trading_name, "Renamed Trading")
        self.assertEqual(self.company.owner_id, self.owner.pk)
        self.assertEqual(self.company.acn, "123456789")
        self.assertEqual(self.company.abn, "12123456789")
        self.assertEqual(self.company.company_type, CompanyType.PROPRIETARY)
