from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from users.models import UserAccount, UserProfile

User = get_user_model()


class UserAccountCreateTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="owner@example.test", password="pw-12345678")
        self.profile = UserProfile.objects.create(user=self.user, full_name="Owner")
        self.client.force_authenticate(self.user)

    def test_individual_account_sets_requester_as_director(self):
        response = self.client.post("/api/user-accounts/", {"accountType": "individual"}, format="json")

        self.assertEqual(response.status_code, 201)
        account = UserAccount.objects.get(uuid=response.json()["uuid"])
        self.assertEqual(account.director_id, self.profile.pk)
        self.assertEqual(list(account.user_profiles.values_list("pk", flat=True)), [self.profile.pk])
        self.assertEqual(response.json()["director"], str(self.profile.pk))

    def test_joint_account_has_no_director_and_ignores_submitted_director(self):
        other_user = User.objects.create_user(email="other@example.test", password="pw-12345678")
        other_profile = UserProfile.objects.create(user=other_user)

        response = self.client.post(
            "/api/user-accounts/",
            {"accountType": "joint", "director": other_profile.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        account = UserAccount.objects.get(uuid=response.json()["uuid"])
        self.assertIsNone(account.director_id)
        self.assertEqual(list(account.user_profiles.values_list("pk", flat=True)), [self.profile.pk])
        self.assertIsNone(response.json()["director"])
