from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connections
from django.test.utils import CaptureQueriesContext
from django.urls import resolve
from rest_framework.test import APIClient, APITransactionTestCase

from documents.models import Document, DocumentType
from feature_flags.models import FeatureFlag
from shared.db import (
    APP_ALIAS,
    atomic,
    current_alias,
    on_commit,
    principal_of,
    use_operator,
)
from shared.services import act_under_row_lock
from shared.tests.scoped import RunsOnTheScopedConnection
from shared.tests.tenants import make_tenant
from shared.tests.test_cross_tenant_routes_under_rls import locking_request_views
from tokens.exceptions import OrderCancellationException
from users.models import UserAccount, UserProfile
from users.services.setup import ensure_defaults

User = get_user_model()
PASSWORD = "scoped-password-123"


class AuthRequestsUseTheAppRoleTest(RunsOnTheScopedConnection, APITransactionTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        with use_operator():
            self.user = User.objects.create_user(
                email="scoped@example.test", password=PASSWORD, is_email_verified=True, is_active=True
            )
            profile, _, _, _ = ensure_defaults(self.user)
            profile.is_signup_completed = True
            profile.save(update_fields=["is_signup_completed"])

    def signin(self, email="scoped@example.test", password=PASSWORD):
        return self.client.post("/api/signin/", {"email": email, "password": password}, format="json")

    def test_completed_user_signs_in_through_the_app_connection_and_keeps_a_cookie_session(self):
        with CaptureQueriesContext(connections[APP_ALIAS]) as queries:
            response = self.signin()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(any('"users_userprofile"' in item["sql"] for item in queries))
        self.assertIn("access", response.cookies)
        identity = self.client.get("/api/auth/verify/")
        self.assertEqual(identity.status_code, 200, identity.content)
        self.assertTrue(identity.json()["valid"])
        self.assertIn(principal_of(APP_ALIAS), (None, ""))

    def test_new_signup_commits_its_profile_account_membership_and_preferences(self):
        with patch("authentication.views.user.EmailCodeService.send") as send_email:
            response = self.client.post(
                "/api/signup/",
                {"email": "new-scoped@example.test", "password": PASSWORD, "passwordConfirm": PASSWORD},
                format="json",
            )
        self.assertEqual(response.status_code, 201, response.content)
        with use_operator():
            user = User.objects.get(email="new-scoped@example.test")
            profile = UserProfile.objects.get(user=user)
            account = profile.user_accounts.get()
            self.assertEqual(account.director_id, profile.pk)
            self.assertTrue(account.portfolios.exists())
            self.assertFalse(profile.is_signup_completed)
        send_email.assert_called_once()
        self.assertIn(principal_of(APP_ALIAS), (None, ""))

    def test_failed_signup_rolls_back_all_defaults_on_the_app_connection(self):
        with patch(
            "users.services.setup.RiskAssessmentService.create_pending_assessment", side_effect=RuntimeError("probe")
        ), patch("authentication.views.user.EmailCodeService.send") as send_email:
            response = self.client.post(
                "/api/signup/",
                {"email": "rolled-back@example.test", "password": PASSWORD, "passwordConfirm": PASSWORD},
                format="json",
            )
        self.assertEqual(response.status_code, 500, response.content)
        with use_operator():
            self.assertFalse(User.objects.filter(email="rolled-back@example.test").exists())
            self.assertEqual(UserProfile.objects.count(), 1)
            self.assertEqual(UserAccount.objects.count(), 1)
        send_email.assert_not_called()

    def test_incomplete_signup_is_refused_for_the_business_reason(self):
        with use_operator():
            UserProfile.objects.filter(user=self.user).update(is_signup_completed=False)
        response = self.signin()
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("complete your signup", str(response.json()))
        self.assertIn(principal_of(APP_ALIAS), (None, ""))

    def test_anonymous_request_after_signin_cannot_inherit_the_previous_principal(self):
        self.assertEqual(self.signin().status_code, 200)
        response = APIClient().get("/api/wallets/")
        self.assertEqual(response.status_code, 401, response.content)
        self.assertIn(principal_of(APP_ALIAS), (None, ""))


class RequestTransactionsUseTheAppRoleTest(RunsOnTheScopedConnection, APITransactionTestCase):
    def setUp(self):
        with use_operator():
            self.user = User.objects.create_user(email="atomic-scoped@example.test", password=PASSWORD, is_active=True)
            self.profile = UserProfile.objects.create(user=self.user)
            self.flag = FeatureFlag.objects.create(name="scoped-row-lock", enabled=False)
        self.signed_in_as(self.user)

    def upload(self):
        return self.client.post(
            "/api/v1/documents/",
            {
                "documentType": DocumentType.PAYSLIP,
                "file": SimpleUploadedFile("scoped.pdf", b"%PDF-1.4 scoped", content_type="application/pdf"),
            },
            format="multipart",
        )

    def test_failed_account_creation_leaves_no_unlinked_row_visible_to_the_operator(self):
        with patch(
            "users.services.accounts.RiskAssessmentService.create_pending_assessment", side_effect=RuntimeError("probe")
        ):
            response = self.client.post("/api/user-accounts/", {"accountType": "individual"}, format="json")
        self.assertEqual(response.status_code, 500, response.content)
        with use_operator():
            self.assertEqual(UserAccount.objects.count(), 0)

    def test_successful_account_creation_commits_the_profile_link(self):
        response = self.client.post("/api/user-accounts/", {"accountType": "individual"}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        with use_operator():
            account = UserAccount.objects.get(uuid=response.json()["uuid"])
            self.assertEqual(list(account.user_profiles.values_list("pk", flat=True)), [self.profile.pk])

    def test_joint_account_retains_no_director_and_cannot_link_a_client_supplied_profile(self):
        with use_operator():
            other = User.objects.create_user(email="foreign-director@example.test", password=PASSWORD)
            foreign_profile = UserProfile.objects.create(user=other)
        response = self.client.post(
            "/api/user-accounts/", {"accountType": "joint", "director": str(foreign_profile.pk)}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        with use_operator():
            account = UserAccount.objects.get(uuid=response.json()["uuid"])
            self.assertIsNone(account.director_id)
            self.assertEqual(list(account.user_profiles.values_list("pk", flat=True)), [self.profile.pk])

    def test_failed_document_enqueue_leaves_no_row_on_either_connection(self):
        with patch("documents.services.document.extract_document.defer", side_effect=RuntimeError("probe")) as defer:
            response = self.upload()
        self.assertEqual(response.status_code, 500, response.content)
        defer.assert_called_once()
        with use_operator():
            self.assertEqual(Document.objects.count(), 0)

    def test_document_enqueue_observes_the_app_transaction_that_writes_the_row(self):
        seen = []

        def enqueue(**kwargs):
            seen.append((current_alias(), connections[APP_ALIAS].in_atomic_block, Document.objects.count()))

        with patch("documents.services.document.extract_document.defer", side_effect=enqueue):
            response = self.upload()
        self.assertEqual(response.status_code, 202, response.content)
        self.assertEqual(seen, [(APP_ALIAS, True, 1)])
        with use_operator():
            self.assertEqual(Document.objects.count(), 1)

    def test_row_lock_commits_before_returning_a_business_refusal(self):
        committed = []

        def act(row):
            row.enabled = True
            row.save(update_fields=["enabled"])
            on_commit(lambda: committed.append(current_alias()))
            return row, OrderCancellationException("refused after the write")

        with CaptureQueriesContext(connections[APP_ALIAS]) as queries:
            with self.assertRaises(OrderCancellationException):
                act_under_row_lock(FeatureFlag.objects.all(), self.flag.pk, act)
        self.assertTrue(any("FOR UPDATE" in item["sql"] for item in queries))
        self.assertEqual(committed, [APP_ALIAS])
        with use_operator():
            self.assertTrue(FeatureFlag.objects.get(pk=self.flag.pk).enabled)

    def test_row_lock_and_outer_transaction_roll_back_on_the_same_connection(self):
        def act(row):
            row.enabled = True
            row.save(update_fields=["enabled"])
            return row, None

        with self.assertRaisesRegex(RuntimeError, "outer failure"):
            with atomic():
                act_under_row_lock(FeatureFlag.objects.all(), self.flag.pk, act)
                raise RuntimeError("outer failure")
        with use_operator():
            self.assertFalse(FeatureFlag.objects.get(pk=self.flag.pk).enabled)


class LockedUpdatesUseTheAppRoleTest(RunsOnTheScopedConnection, APITransactionTestCase):
    def setUp(self):
        with use_operator():
            self.tenant = make_tenant("locked-update")
        self.signed_in_as(self.tenant.user)

    def test_every_locking_view_runs_without_a_transaction_supplied_by_the_test(self):
        routes = (
            ("user-profiles", "profile", {"fullName": "Scoped update"}),
            ("financial-profiles", "financial_profile", {}),
            ("user-accounts", "account", {"accountType": "individual"}),
            ("wallets", "wallet", {"name": "Scoped update"}),
        )
        covered = set()
        for resource, field, payload in routes:
            url = f"/api/{resource}/{getattr(self.tenant, field).uuid}/"
            with self.subTest(url=url):
                self.assertFalse(connections[APP_ALIAS].in_atomic_block)
                with CaptureQueriesContext(connections[APP_ALIAS]) as queries:
                    response = self.client.patch(url, payload, format="json")
                self.assertEqual(response.status_code, 200, response.content)
                self.assertTrue(any("FOR UPDATE" in item["sql"] for item in queries), url)
                view = resolve(url).func.cls
                covered.add(f"{view.__module__}.{view.__name__}")
        self.assertEqual(covered, locking_request_views())
        with use_operator():
            self.tenant.profile.refresh_from_db()
            self.assertEqual(self.tenant.profile.full_name, "Scoped update")
