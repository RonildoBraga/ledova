from django.contrib.auth import get_user_model
from djangorestframework_camel_case.util import camelize
from rest_framework.test import APITestCase

from users.models import UserProfile
from users.serializers import UserProfileSerializer

User = get_user_model()


class UserProfileContractTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="contract@example.test", password="pw-12345678")
        self.profile = UserProfile.objects.create(
            user=self.user, kyc_provider="sumsub", sumsub_verification_status="pending"
        )
        self.client.force_authenticate(self.user)

    def test_list_keeps_the_keys_clients_read_and_drops_the_duplicate_kyc_columns(self):
        body = self.client.get("/api/user-profiles/").json()

        row = body["results"][0]
        self.assertEqual(set(row), set(camelize({name: None for name in UserProfileSerializer.Meta.fields})))
        self.assertTrue(
            {"uuid", "fullName", "email", "isIdVerified", "kycProvider", "verificationStatus", "reviewResult"}
            <= set(row)
        )
        self.assertEqual(row["sumsubVerificationStatus"], "pending")
        for gone in (
            "preScreeningCompletedAt",
            "sumsubReviewResult",
            "sumsubReviewAnswer",
            "sumsubRejectionLabels",
            "sumsubVerifiedAt",
            "kycaidVerificationId",
        ):
            self.assertNotIn(gone, row)

    def test_unknown_query_params_are_ignored_instead_of_erroring(self):
        response = self.client.get("/api/user-profiles/?risk_tolerance=high&verified=true")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["results"]), 1)
