from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITransactionTestCase

from users.models import UserAccount, UserProfile

User = get_user_model()


class UserAccountCreateIsAllOrNothingTest(APITransactionTestCase):

    def setUp(self):
        self.user = User.objects.create_user(email="atomic-owner@example.test", password="pw-12345678")
        self.profile = UserProfile.objects.create(user=self.user, full_name="Owner")
        self.client.force_authenticate(self.user)

    def _create(self):
        return self.client.post("/api/user-accounts/", {"accountType": "individual"}, format="json")

    def test_a_failing_risk_assessment_leaves_no_account_behind(self):
        with patch(
            "users.services.accounts.RiskAssessmentService.create_pending_assessment",
            side_effect=RuntimeError("risk service down"),
        ):
            response = self._create()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(UserAccount.objects.count(), 0)

    def test_a_failure_between_the_insert_and_the_profile_link_leaves_no_account_behind(self):
        with patch("users.views.user_account.register_account", side_effect=RuntimeError("link failed")):
            response = self._create()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(UserAccount.objects.count(), 0)

    def test_an_account_never_survives_without_the_profile_link_it_is_scoped_by(self):
        with patch(
            "users.services.accounts.RiskAssessmentService.create_pending_assessment",
            side_effect=RuntimeError("risk service down"),
        ):
            self._create()

        self.assertFalse(UserAccount.objects.accounts_the_user_is_a_member_of(self.user).exists())
        self.assertEqual(UserAccount.objects.count(), 0)

    def test_the_successful_path_still_commits_the_account_and_its_link(self):
        response = self._create()

        self.assertEqual(response.status_code, 201)
        account = UserAccount.objects.get(uuid=response.json()["uuid"])
        self.assertEqual(list(account.user_profiles.values_list("pk", flat=True)), [self.profile.pk])
        self.assertEqual(account.director_id, self.profile.pk)
