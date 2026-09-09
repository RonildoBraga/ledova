from unittest.mock import patch

from django.db import DatabaseError
from rest_framework.test import APITransactionTestCase

from shared.db import acting_for, atomic, use_operator
from shared.tests.scoped import RunsOnTheScopedConnection
from shared.tests.tenants import make_tenant
from tokens.models import FormerHolder, ShareToken
from tokens.tests.test_a_register_of_former_members import a_cessation


class ScopedFormerMemberPrivacyTest(RunsOnTheScopedConnection, APITransactionTestCase):
    def setUp(self):
        super().setUp()
        with use_operator():
            self.owner = make_tenant("former-owner")
            self.other = make_tenant("former-outsider")
            self.row = a_cessation(
                self.owner.deployed_token, name="Private former member", residential_address="Private address"
            )

    def test_the_owner_can_read_the_former_member(self):
        with acting_for(self.owner.user.pk):
            self.assertEqual(FormerHolder.objects.get(pk=self.row.pk).residential_address, "Private address")

    def test_a_market_viewer_sees_the_share_class_without_its_former_members(self):
        with acting_for(self.other.user.pk):
            self.assertTrue(ShareToken.objects.filter(pk=self.owner.deployed_token.pk).exists())
            self.assertFalse(FormerHolder.objects.filter(pk=self.row.pk).exists())

    def test_the_owner_cannot_rewrite_the_recorded_particulars(self):
        with acting_for(self.owner.user.pk):
            with self.assertRaises(DatabaseError), atomic():
                FormerHolder.objects.filter(pk=self.row.pk).update(name="Rewritten")
        with use_operator():
            self.row.refresh_from_db()
            self.assertEqual(self.row.name, "Private former member")

    def test_the_owner_cannot_insert_a_former_member(self):
        with acting_for(self.owner.user.pk):
            with self.assertRaises(DatabaseError), atomic():
                a_cessation(self.owner.deployed_token, block=200)
        with use_operator():
            self.assertEqual(FormerHolder.objects.filter(token=self.owner.deployed_token).count(), 1)

    def test_the_owner_cannot_delete_the_record_before_its_retention_clock(self):
        with acting_for(self.owner.user.pk):
            removed, _ = FormerHolder.objects.filter(pk=self.row.pk).delete()
            self.assertEqual(removed, 0)
        with use_operator():
            self.assertTrue(FormerHolder.objects.filter(pk=self.row.pk).exists())

    def test_the_owner_can_read_and_export_a_register_with_only_former_members(self):
        self.signed_in_as(self.owner.user)
        with patch("tokens.services.register.ShareTokenService") as provider:
            provider.return_value.transfer_participants.return_value = set()
            provider.return_value.share_supply.return_value = (0, 0)
            provider.return_value.deployment_block.return_value = 1
            response = self.client.get(f"/api/v1/tokens/{self.owner.deployed_token.pk}/holders/")
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.json()["holders"], [])
            former = response.json()["formerMembers"]
            self.assertEqual(len(former), 1)
            self.assertEqual(former[0]["residentialAddress"], "Private address")
            self.assertEqual(former[0]["sharesAtCessation"], "1000")
            self.assertTrue(former[0]["identityRecordedAt"])
            self.assertTrue(response.json()["formerMembersStale"])
            exported = self.client.get(f"/api/v1/tokens/{self.owner.deployed_token.pk}/register/export/")
            self.assertEqual(exported.status_code, 200, exported.content)
            self.assertIn(b"Private former member", exported.content)
            self.assertIn(b"Private address", exported.content)
        with use_operator():
            self.owner.deployed_token.refresh_from_db()
            self.assertIsNone(self.owner.deployed_token.former_holders_folded_at)

    def test_a_market_viewer_cannot_export_or_fetch_the_former_members(self):
        self.signed_in_as(self.other.user)
        for suffix in ("holders/", "register/export/"):
            response = self.client.get(f"/api/v1/tokens/{self.owner.deployed_token.pk}/{suffix}")
            self.assertEqual(response.status_code, 404, response.content)
            self.assertNotIn(b"Private address", response.content)
