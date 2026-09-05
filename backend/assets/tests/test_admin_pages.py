from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from assets.models import Asset, AssetChainDeployment, AssetSnapshot

User = get_user_model()


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=TEST_STORAGES)
class AssetsAdminPagesTest(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser(email="asset-admin@example.test", password="pw-12345678"))
        self.asset = Asset.objects.create(symbol="ADM", name="Admin asset", asset_type="tokenized_security")
        self.deployment = AssetChainDeployment.objects.create(
            asset=self.asset, chain="base", contract_address="0x" + "e" * 40
        )
        self.snapshot = AssetSnapshot.objects.create(
            asset=self.asset, price=Decimal("1"), source_timestamp=timezone.now(), data_source="manual"
        )

    def test_every_assets_model_is_registered_and_renders(self):
        registered = {model for model in admin.site._registry if model._meta.app_label == "assets"}
        instances = [self.asset, self.snapshot]
        self.assertEqual(registered, {type(instance) for instance in instances})

        for instance in instances:
            info = (instance._meta.app_label, instance._meta.model_name)
            with self.subTest(model=instance._meta.label):
                self.assertEqual(self.client.get(reverse("admin:%s_%s_changelist" % info)).status_code, 200)
                self.assertEqual(
                    self.client.get(reverse("admin:%s_%s_change" % info, args=[instance.pk])).status_code, 200
                )
        self.assertEqual(self.client.get(reverse("admin:assets_asset_add")).status_code, 200)

    def test_actions_are_the_five_that_survive(self):
        url = reverse("admin:assets_asset_changelist")
        self.assertEqual(
            list(admin.site._registry[Asset].get_actions(self.client.get(url).wsgi_request)),
            ["delete_selected", "update_prices", "mark_as_active", "mark_as_inactive", "mark_as_verified"],
        )

        self.client.post(url, {"action": "mark_as_inactive", "_selected_action": [self.asset.pk]})
        self.assertFalse(Asset.objects.get(pk=self.asset.pk).is_active)
        self.client.post(url, {"action": "mark_as_active", "_selected_action": [self.asset.pk]})
        self.assertTrue(Asset.objects.get(pk=self.asset.pk).is_active)

        self.assertFalse(self.asset.is_verified)
        self.client.post(url, {"action": "mark_as_verified", "_selected_action": [self.asset.pk]})
        self.assertTrue(Asset.objects.get(pk=self.asset.pk).is_verified)

    def test_update_prices_shows_the_form_then_writes_the_price(self):
        url = reverse("admin:assets_asset_changelist")
        preview = self.client.post(url, {"action": "update_prices", "_selected_action": [self.asset.pk]})
        self.assertEqual(preview.status_code, 200)
        self.assertIn("form", preview.context)

        self.client.post(
            url,
            {
                "action": "update_prices",
                "_selected_action": [self.asset.pk],
                "apply": "1",
                "price": "4.5",
                "currency": "USD",
                "create_snapshot": "on",
            },
        )
        self.assertEqual(Asset.objects.get(pk=self.asset.pk).current_price, Decimal("4.5"))
        self.assertEqual(AssetSnapshot.objects.filter(asset=self.asset, data_source="manual").count(), 2)
