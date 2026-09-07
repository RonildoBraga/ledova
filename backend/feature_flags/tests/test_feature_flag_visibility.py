from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from feature_flags.models import FeatureFlag

User = get_user_model()


class FeatureFlagVisibilityTests(APITestCase):
    def setUp(self):
        self.enabled = FeatureFlag.objects.create(name="enable_dark_mode", enabled=True)
        self.disabled = FeatureFlag.objects.create(name="enable_beta_charts", enabled=False)
        self.user = User.objects.create_user(email="investor@example.com", password="pw")

    def test_queryset_hides_disabled_flags(self):
        visible = FeatureFlag.objects.visible_to_user(self.user)

        self.assertEqual([flag.name for flag in visible], ["enable_dark_mode"])

    def test_queryset_gives_an_anonymous_caller_nothing(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertFalse(FeatureFlag.objects.visible_to_user(AnonymousUser()).exists())
        self.assertFalse(FeatureFlag.objects.visible_to_user(None).exists())

    def test_list_route_serves_only_enabled_flags(self):
        self.client.force_authenticate(self.user)

        response = self.client.get("/api/feature-flags/")

        self.assertEqual(response.status_code, 200)
        names = [row["name"] for row in response.data["results"]]
        self.assertEqual(names, ["enable_dark_mode"])

    def test_detail_route_404s_on_a_disabled_flag(self):
        self.client.force_authenticate(self.user)

        response = self.client.get(f"/api/feature-flags/{self.disabled.uuid}/")

        self.assertEqual(response.status_code, 404)
