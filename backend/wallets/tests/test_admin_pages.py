"""Every wallets ModelAdmin renders; the wallet changelist counts holdings in the list query."""

from decimal import Decimal
from unittest.mock import patch

from django.contrib import admin
from django.test import TestCase, override_settings
from django.urls import reverse

from shared.tests.tenants import make_tenant
from wallets.models import Holding, Wallet

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=TEST_STORAGES)
class WalletsAdminPagesTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant("walletadmin", superuser=True)
        self.client.force_login(self.tenant.user)
        self.instances = [
            self.tenant.wallet,
            self.tenant.holding,
            self.tenant.holding_snapshot,
            self.tenant.transaction,
        ]

    def test_every_wallets_model_is_registered_and_renders(self):
        registered = {model for model in admin.site._registry if model._meta.app_label == "wallets"}
        self.assertEqual(registered, {type(instance) for instance in self.instances})

        for instance in self.instances:
            info = (instance._meta.app_label, instance._meta.model_name)
            with self.subTest(model=instance._meta.label):
                self.assertEqual(self.client.get(reverse("admin:%s_%s_changelist" % info)).status_code, 200)
                self.assertEqual(
                    self.client.get(reverse("admin:%s_%s_change" % info, args=[instance.pk])).status_code, 200
                )
        self.assertEqual(self.client.get(reverse("admin:wallets_wallet_add")).status_code, 200)

    def test_holdings_count_is_annotated_and_survives_the_profile_join_of_search(self):
        Holding.objects.create(wallet=self.tenant.wallet, asset=self.tenant.refs.spare_asset, quantity=Decimal("1"))
        url = reverse("admin:wallets_wallet_changelist")

        response = self.client.get(url, {"q": self.tenant.user.email, "o": "5"})

        counts = {row.pk: row.holdings_count for row in response.context["cl"].result_list}
        self.assertEqual(counts, {self.tenant.wallet.pk: 2, self.tenant.spare_wallet.pk: 0})

    def test_wallet_actions_verify_and_queue_syncs(self):
        url = reverse("admin:wallets_wallet_changelist")
        self.client.post(url, {"action": "verify_wallets", "_selected_action": [self.tenant.spare_wallet.pk]})
        spare = Wallet.objects.get(pk=self.tenant.spare_wallet.pk)
        self.assertTrue(spare.is_verified)
        self.assertIsNotNone(spare.verified_at)

        with patch("wallets.tasks.sync_wallet") as sync_wallet:
            self.client.post(url, {"action": "sync_holdings_action", "_selected_action": [spare.pk]})
        sync_wallet.defer.assert_called_once_with(wallet_uuid=str(spare.uuid))
