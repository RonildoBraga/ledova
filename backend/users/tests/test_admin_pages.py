from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from assets.models import Asset
from portfolios.models import Portfolio
from users.models import (
    DeviceToken,
    FavouriteAsset,
    FinancialProfile,
    Notification,
    NotificationPreferences,
    UserAccount,
    UserPreferences,
    UserProfile,
    Waitlist,
)

User = get_user_model()

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=TEST_STORAGES)
class UsersAdminPagesTest(TestCase):
    """Every users ModelAdmin must still render its changelist, add form and change form."""

    def setUp(self):
        self.admin = User.objects.create_superuser(email="admin@example.test", password="pw-12345678")
        self.client.force_login(self.admin)
        user = User.objects.create_user(email="member@example.test", password="pw-12345678")
        profile = UserProfile.objects.create(user=user, full_name="Member", phone_country_code="+61", phone_number="4")
        account = UserAccount.objects.create(account_number="ADMIN-ACC", director=profile)
        account.user_profiles.add(profile)
        portfolio = Portfolio.objects.create(user_account=account, name="Admin portfolio")
        asset = Asset.objects.create(symbol="ADM", name="Admin asset", asset_type="tokenized_security", is_active=True)
        self.instances = [
            profile,
            account,
            FinancialProfile.objects.create(user_profile=profile, occupation="Tester"),
            UserPreferences.objects.create(
                user_profile=profile, selected_account=account, selected_portfolio=portfolio
            ),
            NotificationPreferences.objects.create(user_profile=profile),
            FavouriteAsset.objects.create(user_account=account, asset=asset),
            DeviceToken.objects.create(user=user, push_token="ExponentPushToken[admin]", device_type="ios"),
            Notification.objects.create(user=user, title="Hello", body="Body"),
            Waitlist.objects.create(email="wait@example.test"),
        ]

    def test_every_users_model_is_registered_and_renders(self):
        registered = {model for model in admin.site._registry if model._meta.app_label == "users"}
        self.assertEqual(registered, {type(instance) for instance in self.instances})

        for instance in self.instances:
            info = (instance._meta.app_label, instance._meta.model_name)
            with self.subTest(model=instance._meta.label):
                self.assertEqual(self.client.get(reverse("admin:%s_%s_changelist" % info)).status_code, 200)
                self.assertEqual(self.client.get(reverse("admin:%s_%s_add" % info)).status_code, 200)
                self.assertEqual(
                    self.client.get(reverse("admin:%s_%s_change" % info, args=[instance.pk])).status_code, 200
                )

    def test_waitlist_actions_still_toggle_entries(self):
        entry = Waitlist.objects.get(email="wait@example.test")
        url = reverse("admin:users_waitlist_changelist")

        self.client.post(url, {"action": "mark_inactive", "_selected_action": [entry.pk]})
        entry.refresh_from_db()
        self.assertFalse(entry.is_active)

        self.client.post(url, {"action": "mark_active", "_selected_action": [entry.pk]})
        entry.refresh_from_db()
        self.assertTrue(entry.is_active)
